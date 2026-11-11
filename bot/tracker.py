"""Solicitações em processamento e seus sinais de cancelamento."""

from __future__ import annotations

import threading


class RequestTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._active: dict[str, threading.Event] = {}

    def start(self, req_id: str) -> threading.Event:
        cancel = threading.Event()
        with self._lock:
            self._active[req_id] = cancel
        return cancel

    def finish(self, req_id: str) -> None:
        with self._lock:
            self._active.pop(req_id, None)

    def cancel(self, req_id: str) -> bool:
        with self._lock:
            event = self._active.get(req_id)
        if event:
            event.set()
        return event is not None

    def cancel_all(self) -> None:
        with self._lock:
            events = list(self._active.values())
        for event in events:
            event.set()

    def active(self) -> list[str]:
        with self._lock:
            return list(self._active)


class BotStats:
    KEYS = ("requests", "answered", "errors")

    def __init__(self):
        self._lock = threading.Lock()
        self._values = dict.fromkeys(self.KEYS, 0)

    def incr(self, key: str) -> None:
        with self._lock:
            self._values[key] += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._values)
