"""Testes da lógica do bot sem rede nem LLM real (modelo falso injetado)."""

import threading
import unittest

from bot.assistant import Assistant
from bot.commands import default_commands
from bot.errors import Cancelled
from bot.history import HistoryStore
from bot.prompts import RESET_TEXT
from bot.streaming import ChunkBuffer


class FakeModel:
    """Implementa a interface ChatModel devolvendo uma resposta previsível."""

    model, timeout, max_time = "falso", 1.0, 1.0

    def __init__(self):
        self.calls: list[list[dict]] = []

    def check(self):
        return ""

    def chat_stream(self, messages, on_delta, cancel):
        self.calls.append(messages)
        answer = f"resposta {len(self.calls)}"
        for word in answer.split():
            on_delta(word + " ")
        return answer


class AssistantTest(unittest.TestCase):
    def setUp(self):
        self.llm = FakeModel()
        self.history = HistoryStore(max_turns=2)
        self.assistant = Assistant(self.llm, self.history, default_commands(self.history))

    def ask(self, user, question, cancel=None):
        deltas, thinking = [], []
        answer = self.assistant.answer(user, question, cancel=cancel or threading.Event(),
                                       on_delta=deltas.append, on_thinking=lambda: thinking.append(True))
        return answer, deltas, thinking

    def test_history_is_per_user_and_limited(self):
        self.ask("Ana", "q1")
        self.ask("Ana", "q2")
        self.ask("Bruno", "b1")
        answer, deltas, thinking = self.ask("Ana", "q3")
        self.assertEqual(answer.history_turns, 2)
        self.assertEqual(deltas, ["resposta ", "4 "])
        self.assertEqual(thinking, [True])
        sent = [m["content"] for m in self.llm.calls[-1] if m["role"] == "user"]
        self.assertEqual(sent, ["q1", "q2", "q3"], "contexto da Ana sem as perguntas do Bruno")
        self.assertIn('"Ana"', self.llm.calls[-1][0]["content"], "prompt de sistema cita o usuário")

    def test_commands_do_not_call_the_llm(self):
        self.ask("Ana", "q1")
        answer, _deltas, thinking = self.ask("Ana", " /RESET ")
        self.assertEqual((answer.text, answer.history_turns), (RESET_TEXT, 0))
        self.assertEqual(thinking, [])
        self.assertEqual(len(self.llm.calls), 1)
        self.assertIn("2 perguntas", self.ask("Ana", "/ajuda")[0].text)

    def test_cancelled_before_calling_the_llm(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            self.ask("Ana", "q1", cancel)
        self.assertEqual(self.llm.calls, [])


class ChunkBufferTest(unittest.TestCase):
    def test_groups_tokens_by_interval(self):
        now = [0.0]
        emitted = []
        buf = ChunkBuffer(emitted.append, interval=0.15, clock=lambda: now[0])
        buf.add("a")
        buf.add("b")
        now[0] = 0.2
        buf.add("c")           # passou o intervalo: envia "abc" de uma vez
        buf.add("d")
        buf.flush()
        buf.flush()            # nada pendente: não envia quadro vazio
        self.assertEqual(emitted, ["abc", "d"])


if __name__ == "__main__":
    unittest.main()
