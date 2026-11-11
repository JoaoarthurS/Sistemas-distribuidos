"""Entrada e saída de participantes (HELLO → WELCOME, USER_JOINED, USER_LEFT)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from common import protocol as P
from common.protocol import ErrorCode

from .bot_broker import BotBroker
from .config import ServerConfig
from .monitor import Monitor
from .registry import ClientRegistry
from .validation import RejectConnection, validate_hello

if TYPE_CHECKING:
    from .connection import ClientConnection


class SessionManager:
    def __init__(self, registry: ClientRegistry, broker: BotBroker, monitor: Monitor, config: ServerConfig):
        self._registry = registry
        self._broker = broker
        self._monitor = monitor
        self._config = config

    def join(self, conn: ClientConnection, hello: dict) -> None:
        """Valida o HELLO, registra o nome e anuncia o participante.

        Lança RejectConnection (depois de enviar ERROR ao cliente) se recusado.
        """
        try:
            identity = validate_hello(hello, self._config.bot_token)
            if not self._registry.claim(conn, identity):
                raise RejectConnection(ErrorCode.NAME_TAKEN, f"o nome '{identity.name}' já está em uso")
        except RejectConnection as exc:
            self._monitor.count("rejected")
            conn.send(P.make(P.ERROR, content=str(exc), code=exc.code, ref=hello.get("id")))
            raise

        conn.send(P.make(P.WELCOME, to=conn.name, ref=hello.get("id"), content=self._welcome(conn)))
        self._registry.broadcast(P.make(P.USER_JOINED, content=conn.public_info()), exclude=conn)
        channel = f"TLS ({conn.tls['version']})" if conn.secure else "TCP sem criptografia"
        self._monitor.event("join", f"{conn.name} entrou como {'bot' if conn.is_bot else 'humano'} "
                                    f"de {conn.address} via {channel}")

    def _welcome(self, conn: ClientConnection) -> dict:
        return {
            "name": conn.name,
            "role": conn.role,
            "secure": conn.secure,
            "tls": conn.tls,
            "users": self._registry.users(),
            "idle_timeout": self._config.idle_timeout,
            "request_timeout": self._config.request_timeout,
            "max_text": P.MAX_TEXT_CHARS,
        }

    def leave(self, conn: ClientConnection, reason: str, registered: bool) -> None:
        """Remove o participante, avisa os demais e resolve as perguntas pendentes."""
        removed = self._registry.release(conn)
        if not (registered and removed):
            self._monitor.event("disconnect", f"{conn.label} ({conn.address}) desconectou: {reason}")
            return

        self._monitor.event("leave", f"{conn.name} saiu: {reason}")
        self._registry.broadcast(P.make(P.USER_LEFT, content={"name": conn.name, "role": conn.role,
                                                               "reason": reason}))
        if conn.is_bot:
            self._broker.bot_left(conn.name)
        else:
            self._broker.user_left(conn.name)
