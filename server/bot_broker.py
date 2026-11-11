"""Intermediação entre usuários e bots.

O BotBroker é a única peça que conhece solicitações pendentes: cria o
req_id, encaminha a pergunta, valida e entrega cada resposta ao solicitante
e expira o que passou do tempo limite.
"""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from common import protocol as P
from common.protocol import ErrorCode

from .monitor import Monitor
from .registry import ClientRegistry

if TYPE_CHECKING:
    from .connection import ClientConnection

QUESTION_PREVIEW_CHARS = 200


@dataclass
class PendingRequest:
    req_id: str
    user: str
    bot: str
    question: str
    ref: str
    created: float = field(default_factory=time.monotonic)
    created_ms: int = field(default_factory=P.now_ms)
    status: str = "na fila"

    def age(self, now: float | None = None) -> float:
        return (now if now is not None else time.monotonic()) - self.created

    def snapshot(self, now: float) -> dict:
        return {"req_id": self.req_id, "user": self.user, "bot": self.bot,
                "question": self.question[:QUESTION_PREVIEW_CHARS], "status": self.status,
                "elapsed": round(self.age(now), 1), "created": self.created_ms}


class BotBroker:
    # status exibido no painel conforme o último quadro recebido do bot
    _STATUS_BY_TYPE = {P.BOT_TYPING: "consultando LLM", P.BOT_CHUNK: "gerando"}

    def __init__(self, registry: ClientRegistry, monitor: Monitor, *,
                 request_timeout: float, max_pending_per_user: int):
        self._registry = registry
        self._monitor = monitor
        self.request_timeout = request_timeout
        self.max_pending_per_user = max_pending_per_user
        self._lock = threading.Lock()
        self._pending: dict[str, PendingRequest] = {}
        self._seq = itertools.count(1)

    # ---- pergunta ----------------------------------------------------------------
    def submit(self, user: ClientConnection, bot: ClientConnection, question: str, msg_id: str) -> None:
        """Cria a solicitação, confirma ao usuário (ACK queued) e encaminha ao bot."""
        if not question:
            user.send(P.make(P.ERROR, to=user.name, ref=msg_id, code=ErrorCode.EMPTY,
                             content=f"escreva a pergunta depois de @{bot.name}"))
            return
        with self._lock:
            busy = sum(1 for pr in self._pending.values() if pr.user == user.name)
            if busy < self.max_pending_per_user:
                req_id = f"R{next(self._seq):04d}"
                self._pending[req_id] = PendingRequest(req_id, user.name, bot.name, question, msg_id)
        if busy >= self.max_pending_per_user:
            user.send(P.make(P.ERROR, to=user.name, ref=msg_id, code=ErrorCode.TOO_MANY_REQUESTS,
                             content=f"aguarde: você já tem {busy} perguntas em andamento"))
            return

        user.send(P.make(P.ACK, to=user.name, ref=msg_id, req_id=req_id,
                         content={"status": "queued", "bot": bot.name}))
        bot.send(P.make(P.BOT_REQUEST, sender=user.name, to=bot.name, req_id=req_id,
                        content=question, ref=msg_id))
        self._monitor.count("bot_requests")
        self._monitor.record("bot_request", user.name, bot.name, question, req_id=req_id, secure=user.secure)
        self._monitor.event("bot", f"{req_id}: {user.name} → {bot.name} (encaminhada ao bot)")

    # ---- resposta ----------------------------------------------------------------
    def deliver(self, bot: ClientConnection, frame: dict) -> None:
        """Repassa BOT_TYPING/CHUNK/RESPONSE/ERROR ao usuário que fez a pergunta."""
        ftype = frame["type"]
        req_id = frame.get("req_id")
        final = ftype in P.BOT_FINAL_TYPES
        with self._lock:
            pr = self._pending.get(req_id)
            valid = pr is not None and pr.bot == bot.name
            if valid:
                if final:
                    del self._pending[req_id]
                else:
                    pr.status = self._STATUS_BY_TYPE.get(ftype, pr.status)
        if not valid:
            if final:
                self._monitor.event("warn", f"{bot.name} respondeu {req_id}, que não está pendente "
                                            f"(expirada ou cancelada) — resposta descartada")
            return
        if frame.get("to") != pr.user:
            self._monitor.event("warn", f"{req_id}: bot indicou destinatário '{frame.get('to')}', "
                                        f"corrigido para o solicitante '{pr.user}'")

        # O destinatário vem da solicitação pendente, não do bot: a resposta
        # só pode chegar a quem perguntou (privacidade + correlação correta).
        user = self._registry.get(pr.user)
        if user:
            user.send(P.make(ftype, sender=bot.name, to=pr.user, req_id=req_id, ref=pr.ref,
                             content=frame.get("content"), code=frame.get("code"), meta=frame.get("meta")))
        if ftype == P.BOT_RESPONSE:
            self._on_answered(bot, pr, frame)
        elif ftype == P.BOT_ERROR:
            self._on_bot_error(bot, pr, frame)

    def _on_answered(self, bot: ClientConnection, pr: PendingRequest, frame: dict) -> None:
        meta = frame.get("meta") or {}
        self._monitor.count("bot_responses")
        self._monitor.record("bot_response", bot.name, pr.user, frame.get("content"), req_id=pr.req_id)
        self._monitor.event("bot", f"{pr.req_id}: resposta entregue a {pr.user} "
                                   f"({meta.get('elapsed_s', '?')} s, "
                                   f"histórico {meta.get('history_turns', '?')} turnos)")

    def _on_bot_error(self, bot: ClientConnection, pr: PendingRequest, frame: dict) -> None:
        self._monitor.count("bot_errors")
        self._monitor.record("bot_error", bot.name, pr.user, frame.get("content"), req_id=pr.req_id)
        self._monitor.event("error", f"{pr.req_id}: bot informou falha ({frame.get('code')}): "
                                     f"{frame.get('content')}")

    # ---- saídas e tempo limite ------------------------------------------------------
    def user_left(self, user: str) -> None:
        """O usuário saiu: o bot pode descartar o processamento."""
        for pr in self._take(lambda pr: pr.user == user):
            bot = self._registry.get(pr.bot)
            if bot:
                bot.send(P.make(P.BOT_CANCEL, to=bot.name, req_id=pr.req_id, content="usuário desconectado"))
            self._monitor.event("bot", f"{pr.req_id} cancelada: {pr.user} desconectou")

    def bot_left(self, bot: str) -> None:
        """O bot caiu: avisa cada usuário que esperava resposta."""
        for pr in self._take(lambda pr: pr.bot == bot):
            self._fail(pr, ErrorCode.BOT_OFFLINE, f"O bot {pr.bot} desconectou antes de responder.",
                       notify_bot=False)

    def expire_overdue(self) -> int:
        """Falha as solicitações que passaram do tempo limite (chamado pelo watchdog)."""
        now = time.monotonic()
        expired = self._take(lambda pr: pr.age(now) > self.request_timeout)
        for pr in expired:
            self._fail(pr, ErrorCode.TIMEOUT,
                       f"O bot não respondeu em {self.request_timeout:g} s (tempo limite do servidor).",
                       notify_bot=True)
        return len(expired)

    def _take(self, predicate) -> list[PendingRequest]:
        with self._lock:
            taken = [pr for pr in self._pending.values() if predicate(pr)]
            for pr in taken:
                del self._pending[pr.req_id]
        return taken

    def _fail(self, pr: PendingRequest, code: str, message: str, notify_bot: bool) -> None:
        user = self._registry.get(pr.user)
        if user:
            user.send(P.make(P.BOT_ERROR, sender=pr.bot, to=pr.user, req_id=pr.req_id,
                             ref=pr.ref, code=code, content=message))
        if notify_bot:
            bot = self._registry.get(pr.bot)
            if bot:
                bot.send(P.make(P.BOT_CANCEL, to=bot.name, req_id=pr.req_id, content=code))
        self._monitor.count("bot_errors")
        if code == ErrorCode.TIMEOUT:
            self._monitor.count("bot_timeouts")
        self._monitor.record("bot_error", pr.bot, pr.user, message, req_id=pr.req_id)
        self._monitor.event("timeout" if code == ErrorCode.TIMEOUT else "error",
                            f"{pr.req_id} ({pr.user}): {message}")

    # ---- painel ---------------------------------------------------------------------
    def snapshot(self) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            return [pr.snapshot(now) for pr in self._pending.values()]
