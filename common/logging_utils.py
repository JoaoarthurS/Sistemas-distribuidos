"""Configuração de log comum ao servidor e ao bot."""

from __future__ import annotations

import logging
import sys


def setup_logging(thread_width: int = 18, level: int = logging.INFO) -> None:
    """Log no console com horário e nome da thread (útil para mostrar a concorrência).

    Também força UTF-8 na saída: o console do Windows usa outra codificação
    por padrão e quebraria acentos e emojis.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=level, datefmt="%H:%M:%S",
                        format=f"%(asctime)s [%(threadName)-{thread_width}s] %(message)s")
