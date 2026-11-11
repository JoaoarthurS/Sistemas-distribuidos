"""Linha de comando do bot — raiz de composição.

Único lugar que lê argumentos/variáveis de ambiente e escolhe as
implementações concretas (OllamaClient, contexto TLS, conexão).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path

from common import tls
from common.logging_utils import setup_logging

from .app import ChatBot
from .assistant import Assistant
from .commands import default_commands
from .config import PLAIN_PORT, TLS_PORT, BotConfig
from .connection import BotConnection, ca_label
from .console import BotConsole
from .history import HistoryStore
from .llm import OllamaClient

log = logging.getLogger("bot")


def parse_args(argv=None) -> BotConfig:
    d = BotConfig()
    ap = argparse.ArgumentParser(prog="python -m bot", description="Bot do SD Chat com LLM local (Ollama)")
    ap.add_argument("--host", default=d.host, help="endereço do servidor")
    ap.add_argument("--port", type=int, default=None,
                    help=f"porta (padrão: {TLS_PORT} com TLS, {PLAIN_PORT} com --plain)")
    ap.add_argument("--plain", action="store_true", help="conecta sem TLS (apenas para comparação)")
    ap.add_argument("--ca", default=str(d.ca), help="certificado da CA usado para validar o servidor")
    ap.add_argument("--name", default=d.name, help="nome do bot no chat (usado na menção @nome)")
    ap.add_argument("--token", default=os.environ.get("CHAT_BOT_TOKEN", d.token), help="token do bot")
    ap.add_argument("--ollama", default=os.environ.get("OLLAMA_URL", d.ollama_url), help="URL do Ollama")
    ap.add_argument("--model", default=os.environ.get("BOT_MODEL", d.model), help="modelo do Ollama")
    ap.add_argument("--llm-timeout", type=float, default=d.llm_timeout,
                    help="tempo máximo (s) esperando a LLM enviar dados (primeiro token ou entre tokens)")
    ap.add_argument("--llm-max-time", type=float, default=d.llm_max_time,
                    help="duração máxima (s) de uma resposta completa")
    ap.add_argument("--history", type=int, default=d.history_turns,
                    help="turnos (pergunta+resposta) lembrados por usuário")
    ap.add_argument("--workers", type=int, default=d.workers, help="threads do pool que processam solicitações")
    ap.add_argument("--temperature", type=float, default=d.temperature)
    ap.add_argument("--max-tokens", type=int, default=d.max_tokens, help="limite de tokens por resposta")
    a = ap.parse_args(argv)
    port = a.port if a.port is not None else (PLAIN_PORT if a.plain else TLS_PORT)
    return BotConfig(host=a.host, port=port, plain=a.plain, ca=Path(a.ca), name=a.name, token=a.token,
                     ollama_url=a.ollama, model=a.model, llm_timeout=a.llm_timeout,
                     llm_max_time=a.llm_max_time, history_turns=a.history, workers=a.workers,
                     temperature=a.temperature, max_tokens=a.max_tokens)


def build_bot(config: BotConfig) -> ChatBot:
    llm = OllamaClient(config.ollama_url, config.model, timeout=config.llm_timeout,
                       max_time=config.llm_max_time, temperature=config.temperature,
                       max_tokens=config.max_tokens)
    history = HistoryStore(config.history_turns)
    assistant = Assistant(llm, history, default_commands(history))
    ssl_context = None if config.plain else tls.client_context(config.ca)

    def connect() -> BotConnection:
        return BotConnection(config.host, config.port, ssl_context, ca_label=ca_label(config.ca))

    return ChatBot(config, assistant, connect)


def main(argv=None) -> int:
    setup_logging(thread_width=14)
    threading.current_thread().name = "principal"
    config = parse_args(argv)
    try:
        bot = build_bot(config)
    except (FileNotFoundError, OSError) as exc:
        sys.exit(f"[ERRO] não foi possível carregar a CA {config.ca} ({exc}). "
                 f"Gere os certificados com: python certs/gen_certs.py")

    if sys.stdin and sys.stdin.isatty():
        threading.Thread(target=BotConsole(bot).run, name="console", daemon=True).start()
    # A conexão roda em uma thread própria; a principal só espera, assim o
    # Ctrl+C funciona mesmo com a leitora bloqueada em recv() (Windows).
    worker = threading.Thread(target=bot.run, name="leitor-socket", daemon=True)
    worker.start()
    try:
        while worker.is_alive():
            worker.join(0.5)
    except KeyboardInterrupt:
        bot.shutdown()
        log.info("bot encerrado")
    return 0
