"""Histórico curto de conversa, separado por usuário."""

from __future__ import annotations

import threading
from collections import deque

MAX_STORED_CHARS = 2000


class HistoryStore:
    """Guarda os últimos N turnos (pergunta + resposta) de cada usuário.

    Um deque separado por usuário garante que os contextos não se misturam.
    O lock protege o dicionário, acessado por várias threads do pool.
    """

    def __init__(self, max_turns: int, max_chars: int = MAX_STORED_CHARS):
        self.max_turns = max_turns
        self.max_chars = max_chars
        self._lock = threading.Lock()
        self._turns: dict[str, deque] = {}
        self._user_locks: dict[str, threading.Lock] = {}

    def messages(self, user: str) -> list[dict]:
        """Turnos anteriores no formato de mensagens da API de chat."""
        with self._lock:
            turns = list(self._turns.get(user, ()))
        out = []
        for question, answer in turns:
            out.append({"role": "user", "content": question})
            out.append({"role": "assistant", "content": answer})
        return out

    def add(self, user: str, question: str, answer: str) -> int:
        """Acrescenta um turno e devolve quantos turnos o usuário tem agora."""
        with self._lock:
            dq = self._turns.setdefault(user, deque(maxlen=self.max_turns))
            dq.append((question[: self.max_chars], answer[: self.max_chars]))
            return len(dq)

    def size(self, user: str) -> int:
        with self._lock:
            return len(self._turns.get(user, ()))

    def clear(self, user: str) -> None:
        with self._lock:
            self._turns.pop(user, None)

    def user_lock(self, user: str) -> threading.Lock:
        """Lock por usuário: perguntas do mesmo usuário são processadas em
        ordem (o contexto fica consistente); usuários diferentes, em paralelo."""
        with self._lock:
            return self._user_locks.setdefault(user, threading.Lock())

    def summary(self) -> dict[str, int]:
        with self._lock:
            return {u: len(d) for u, d in self._turns.items()}
