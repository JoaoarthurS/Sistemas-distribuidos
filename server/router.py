"""Roteamento dos quadros recebidos de participantes já identificados.

Cada tipo de quadro tem um tratador registrado numa tabela, junto com os
papéis autorizados a enviá-lo. Suportar um novo tipo é registrar um novo
tratador — o método route() não muda (princípio aberto/fechado).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from common import protocol as P
from common.protocol import ErrorCode

from .bot_broker import BotBroker
from .monitor import Monitor
from .registry import ClientRegistry
from .validation import parse_mention

if TYPE_CHECKING:
    from .connection import ClientConnection

FrameHandler = Callable[["ClientConnection", dict], None]
MSG_ID_MAX = 40


class MessageRouter:
    def __init__(self, registry: ClientRegistry, broker: BotBroker, monitor: Monitor, *, bot_name: str):
        self._registry = registry
        self._broker = broker
        self._monitor = monitor
        self._bot_name = bot_name
        self._routes: dict[str, tuple[FrameHandler, frozenset[str]]] = {}
        self.register(P.PING, self._on_ping)
        self.register(P.LIST, self._on_list)
        self.register(P.MSG, self._on_message, roles=[P.ROLE_HUMAN])
        self.register(P.TYPING, self._on_typing, roles=[P.ROLE_HUMAN])
        for reply_type in P.BOT_REPLY_TYPES:
            self.register(reply_type, broker.deliver, roles=[P.ROLE_BOT])

    def register(self, frame_type: str, handler: FrameHandler, roles: Iterable[str] = P.ROLES) -> None:
        self._routes[frame_type] = (handler, frozenset(roles))

    def route(self, conn: ClientConnection, frame: dict) -> None:
        ftype = frame.get("type")
        handler, roles = self._routes.get(ftype, (None, frozenset()))
        if handler is None or conn.role not in roles:
            conn.send(P.make(P.ERROR, to=conn.name, ref=frame.get("id"), code=ErrorCode.BAD_TYPE,
                             content=f"tipo '{ftype}' não permitido para {conn.role}"))
            return
        handler(conn, frame)

    # ---- tratadores simples --------------------------------------------------------
    def _on_ping(self, conn: ClientConnection, frame: dict) -> None:
        conn.send(P.make(P.PONG, to=conn.name, ref=frame.get("id")))

    def _on_list(self, conn: ClientConnection, frame: dict) -> None:
        conn.send(P.make(P.USER_LIST, to=conn.name, content=self._registry.users(), ref=frame.get("id")))

    def _on_typing(self, conn: ClientConnection, frame: dict) -> None:
        to = str(frame.get("to") or P.BROADCAST)
        out = P.make(P.TYPING, sender=conn.name, to=to, content=bool(frame.get("content")))
        if to == P.BROADCAST:
            self._registry.broadcast(out, exclude=conn, humans_only=True)
            return
        target = self._registry.get(to)
        if target and target.is_human:
            target.send(out)

    # ---- mensagens ---------------------------------------------------------------------
    def _on_message(self, conn: ClientConnection, frame: dict) -> None:
        msg_id = str(frame.get("id") or P.new_id())[:MSG_ID_MAX]
        to = str(frame.get("to") or P.BROADCAST)
        content = frame.get("content")
        if not self._check_text(conn, msg_id, content):
            return
        if self._try_bot_request(conn, to, content, msg_id):
            return
        if to == P.BROADCAST:
            self._deliver_public(conn, content, msg_id)
        else:
            self._deliver_private(conn, to, content, msg_id)

    def _check_text(self, conn: ClientConnection, msg_id: str, content) -> bool:
        if not isinstance(content, str) or not content.strip():
            self._error(conn, msg_id, ErrorCode.EMPTY, "mensagem vazia")
            return False
        if len(content) > P.MAX_TEXT_CHARS:
            self._error(conn, msg_id, ErrorCode.TOO_LONG, f"mensagem acima de {P.MAX_TEXT_CHARS} caracteres")
            return False
        return True

    def _try_bot_request(self, conn: ClientConnection, to: str, content: str, msg_id: str) -> bool:
        """Trata a mensagem como pergunta ao bot quando o destinatário é um bot
        ou o texto começa com @bot. Devolve True se a mensagem foi consumida."""
        target = self._registry.get(to) if to != P.BROADCAST else None
        mention = parse_mention(content)
        if target and target.is_bot:
            question = mention.text if mention and mention.targets(target.name) else content
            self._broker.submit(conn, target, question.strip(), msg_id)
            return True
        if mention:
            mentioned = self._registry.get(mention.name)
            if mentioned and mentioned.is_bot:
                self._broker.submit(conn, mentioned, mention.text.strip(), msg_id)
                return True
        wants_bot = (target is None and to.lower() == self._bot_name.lower()) or \
                    (mention is not None and mention.targets(self._bot_name))
        if wants_bot:
            conn.send(P.make(P.BOT_ERROR, sender=self._bot_name, to=conn.name, ref=msg_id,
                             code=ErrorCode.BOT_OFFLINE, content="Nenhum bot está conectado no momento."))
            self._monitor.event("bot", f"{conn.name} chamou @{self._bot_name}, mas nenhum bot está conectado")
            return True
        return False

    def _deliver_public(self, conn: ClientConnection, content: str, msg_id: str) -> None:
        out = P.make(P.MSG, sender=conn.name, to=P.BROADCAST, content=content, id=msg_id)
        recipients = self._registry.broadcast(out, exclude=conn, humans_only=True)
        self._ack(conn, msg_id, recipients)
        self._monitor.count("messages_public")
        self._monitor.record("public", conn.name, "todos", content, secure=conn.secure)

    def _deliver_private(self, conn: ClientConnection, to: str, content: str, msg_id: str) -> None:
        target = self._registry.get(to)
        if not target or not target.is_human:
            self._error(conn, msg_id, ErrorCode.USER_NOT_FOUND, f"'{to}' não está online")
            return
        target.send(P.make(P.MSG, sender=conn.name, to=target.name, content=content, id=msg_id))
        self._ack(conn, msg_id, 1)
        self._monitor.count("messages_private")
        self._monitor.record("private", conn.name, target.name, content, secure=conn.secure)

    # ---- respostas ao remetente -------------------------------------------------------
    @staticmethod
    def _ack(conn: ClientConnection, msg_id: str, recipients: int) -> None:
        conn.send(P.make(P.ACK, to=conn.name, ref=msg_id,
                         content={"status": "delivered", "recipients": recipients}))

    @staticmethod
    def _error(conn: ClientConnection, msg_id: str, code: str, message: str) -> None:
        conn.send(P.make(P.ERROR, to=conn.name, ref=msg_id, code=code, content=message))
