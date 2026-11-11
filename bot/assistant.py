"""Regra de negócio do bot, independente de rede: comandos, histórico e LLM."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from .commands import CommandRegistry
from .errors import Cancelled
from .history import HistoryStore
from .llm import ChatModel, DeltaCallback
from .prompts import SYSTEM_PROMPT


@dataclass(frozen=True)
class Answer:
    text: str
    history_turns: int


class Assistant:
    def __init__(self, llm: ChatModel, history: HistoryStore, commands: CommandRegistry,
                 system_prompt: str = SYSTEM_PROMPT):
        self.llm = llm
        self.history = history
        self._commands = commands
        self._system_prompt = system_prompt

    def answer(self, user: str, question: str, *, cancel: threading.Event,
               on_delta: DeltaCallback, on_thinking: Callable[[], object] = lambda: None) -> Answer:
        """Responde a um comando ou consulta a LLM com o histórico do usuário.

        on_thinking é chamado quando a consulta à LLM vai começar (o bot envia
        BOT_TYPING); comandos respondem na hora, sem chamá-lo.
        """
        command = self._commands.resolve(question)
        if command:
            text = command(user)
            return Answer(text, self.history.size(user))

        on_thinking()
        # Perguntas do mesmo usuário em ordem: o contexto fica consistente.
        with self.history.user_lock(user):
            if cancel.is_set():
                raise Cancelled()
            text = self.llm.chat_stream(self._conversation(user, question), on_delta, cancel)
            turns = self.history.add(user, question, text)
        return Answer(text, turns)

    def _conversation(self, user: str, question: str) -> list[dict]:
        return ([{"role": "system", "content": self._system_prompt.format(user=user)}]
                + self.history.messages(user)
                + [{"role": "user", "content": question}])
