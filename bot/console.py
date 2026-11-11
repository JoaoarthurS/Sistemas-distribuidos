"""Console do bot: comandos digitados no terminal (úteis na demonstração)."""

from __future__ import annotations

from collections.abc import Callable

from .app import ChatBot

HELP = ("  status              estado do bot e históricos\n"
        "  timeout <seg>       tempo máximo esperando a LLM (ex.: 'timeout 1' força falha)\n"
        "  modelo <nome>       troca o modelo do Ollama\n"
        "  reset <usuário>     apaga o histórico de um usuário\n"
        "  sair                encerra o bot")


class BotConsole:
    def __init__(self, bot: ChatBot, output: Callable[[str], None] = print,
                 read_line: Callable[[], str] = input):
        self._bot = bot
        self._llm = bot.assistant.llm
        self._history = bot.assistant.history
        self._out = output
        self._read = read_line
        # comando -> (precisa de argumento?, tratador); devolve False para encerrar o console
        self._commands: dict[str, tuple[bool, Callable[[str], bool]]] = {}
        self.register(["ajuda", "help"], self._help)
        self.register(["status"], self._status)
        self.register(["timeout"], self._timeout, needs_arg=True)
        self.register(["modelo"], self._model, needs_arg=True)
        self.register(["reset"], self._reset, needs_arg=True)
        self.register(["sair", "quit", "exit"], self._quit)

    def register(self, names: list[str], handler: Callable[[str], bool], needs_arg: bool = False) -> None:
        for name in names:
            self._commands[name] = (needs_arg, handler)

    def run(self) -> None:
        self._out("Console do bot: digite 'ajuda' para ver os comandos.")
        while not self._bot.stop_event.is_set():
            try:
                line = self._read().strip()
            except (EOFError, KeyboardInterrupt):
                return
            if line and not self.execute(line):
                return

    def execute(self, line: str) -> bool:
        cmd, _, arg = line.partition(" ")
        needs_arg, handler = self._commands.get(cmd.lower(), (False, None))
        if handler is None or (needs_arg and not arg.strip()):
            self._out("  comando desconhecido (digite 'ajuda')")
            return True
        return handler(arg.strip())

    # ---- comandos ----------------------------------------------------------------------
    def _help(self, _arg: str) -> bool:
        self._out(HELP)
        return True

    def _status(self, _arg: str) -> bool:
        bot = self._bot
        self._out(f"  conectado={bot.connected.is_set()} modelo={self._llm.model} "
                  f"timeout={self._llm.timeout:g}s máx={self._llm.max_time:g}s "
                  f"ativas={bot.requests.active()} estatísticas={bot.stats.snapshot()}")
        self._out(f"  históricos (turnos por usuário, limite {self._history.max_turns}): "
                  f"{self._history.summary()}")
        return True

    def _timeout(self, arg: str) -> bool:
        try:
            self._llm.timeout = float(arg)
            self._out(f"  tempo limite da LLM = {self._llm.timeout:g} s")
        except ValueError:
            self._out("  valor inválido")
        return True

    def _model(self, arg: str) -> bool:
        self._llm.model = arg
        self._out(f"  modelo = {self._llm.model}")
        return True

    def _reset(self, arg: str) -> bool:
        self._history.clear(arg)
        self._out(f"  histórico de {arg} apagado")
        return True

    def _quit(self, _arg: str) -> bool:
        self._bot.shutdown()
        return False
