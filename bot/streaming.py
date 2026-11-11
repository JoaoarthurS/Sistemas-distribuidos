"""Agrupamento dos tokens gerados pela LLM antes de enviá-los pela rede."""

from __future__ import annotations

import time
from collections.abc import Callable

DEFAULT_INTERVAL = 0.15  # s


class ChunkBuffer:
    """Acumula pedaços e chama emit(texto) no máximo a cada `interval` segundos.

    Evita um quadro BOT_CHUNK por token. Não conhece sockets nem o protocolo:
    quem cria o buffer decide o que emit faz.
    """

    def __init__(self, emit: Callable[[str], object], interval: float = DEFAULT_INTERVAL,
                 clock: Callable[[], float] = time.monotonic):
        self._emit = emit
        self._interval = interval
        self._clock = clock
        self._parts: list[str] = []
        self._last = clock()

    def add(self, delta: str) -> None:
        self._parts.append(delta)
        if self._clock() - self._last >= self._interval:
            self.flush()

    def flush(self) -> None:
        if self._parts:
            self._emit("".join(self._parts))
            self._parts.clear()
        self._last = self._clock()
