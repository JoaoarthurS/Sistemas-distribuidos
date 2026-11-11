"""Comandos que o usuário envia ao bot (ex.: @bot /reset).

Novos comandos são registrados sem alterar o Assistant (aberto/fechado).
"""

from __future__ import annotations

from collections.abc import Callable

from .history import HistoryStore
from .prompts import HELP_TEXT, RESET_TEXT

CommandHandler = Callable[[str], str]  # recebe o usuário, devolve a resposta


class CommandRegistry:
    def __init__(self):
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, *names: str, handler: CommandHandler) -> None:
        for name in names:
            self._handlers[name.lower()] = handler

    def resolve(self, text: str) -> CommandHandler | None:
        return self._handlers.get(text.strip().lower())

    def names(self) -> list[str]:
        return sorted(self._handlers)


def default_commands(history: HistoryStore) -> CommandRegistry:
    def reset(user: str) -> str:
        history.clear(user)
        return RESET_TEXT

    def help_(_user: str) -> str:
        return HELP_TEXT.format(turns=history.max_turns)

    registry = CommandRegistry()
    registry.register("/reset", "/limpar", "reset", handler=reset)
    registry.register("/ajuda", "/help", "ajuda", handler=help_)
    return registry
