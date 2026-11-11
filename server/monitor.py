"""Observabilidade do servidor: estatísticas e feed de atividade para o painel.

O feed segue o padrão Observer (publish/subscribe): os componentes publicam
eventos sem saber quem os consome; cada navegador com o painel aberto é um
assinante com fila própria.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections import deque

from common import protocol as P

log = logging.getLogger("server")

STAT_KEYS = ("connections_total", "messages_public", "messages_private", "bot_requests",
             "bot_responses", "bot_errors", "bot_timeouts", "rejected")
RECORD_PREVIEW_CHARS = 1200


class Stats:
    """Contadores incrementados por várias threads."""

    def __init__(self, keys=STAT_KEYS):
        self._lock = threading.Lock()
        self._values = dict.fromkeys(keys, 0)

    def incr(self, key: str, n: int = 1) -> None:
        with self._lock:
            self._values[key] += n

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._values)


class ActivityFeed:
    """Histórico recente + entrega em tempo real para os assinantes (SSE)."""

    def __init__(self, max_events: int = 400, max_messages: int = 600, subscriber_queue: int = 1000):
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []
        self._events: deque = deque(maxlen=max_events)
        self._messages: deque = deque(maxlen=max_messages)
        self._queue_size = subscriber_queue

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=self._queue_size)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, kind: str, item: dict) -> None:
        with self._lock:
            (self._events if kind == "event" else self._messages).append(item)
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait((kind, item))
            except queue.Full:
                pass  # navegador lento: perde itens, mas recebe o snapshot periódico

    def recent(self) -> dict:
        with self._lock:
            return {"events": list(self._events), "messages": list(self._messages)}


class Monitor:
    """Fachada usada pelos componentes para registrar o que acontece no servidor."""

    def __init__(self, feed: ActivityFeed | None = None, stats: Stats | None = None,
                 logger: logging.Logger = log):
        self.feed = feed or ActivityFeed()
        self.stats = stats or Stats()
        self._log = logger

    def count(self, key: str, n: int = 1) -> None:
        self.stats.incr(key, n)

    def event(self, kind: str, text: str) -> None:
        """Evento de ciclo de vida (conexão, TLS, entrada, erro...)."""
        self._log.info("[%s] %s", kind.upper(), text)
        self.feed.publish("event", {"ts": P.now_ms(), "kind": kind, "text": text,
                                    "thread": threading.current_thread().name})

    def record(self, kind: str, sender: str, to: str, content, req_id: str | None = None,
               secure: bool | None = None) -> None:
        """Mensagem roteada (pública, privada, pergunta/resposta do bot, aviso)."""
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        self.feed.publish("message", {
            "ts": P.now_ms(), "kind": kind, "from": sender, "to": to,
            "content": text[:RECORD_PREVIEW_CHARS], "req_id": req_id, "secure": secure,
        })
