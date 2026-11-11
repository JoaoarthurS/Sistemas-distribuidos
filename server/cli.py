"""Linha de comando do servidor — raiz de composição.

É o único lugar que lê argumentos/variáveis de ambiente e instancia as
classes concretas (contexto TLS, ChatServer, painel); as demais peças
recebem suas dependências prontas.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

from common import tls
from common.logging_utils import setup_logging

from .chat_server import ChatServer
from .config import ServerConfig
from .dashboard import DashboardServer
from .listener import ListenerError

log = logging.getLogger("server")


def parse_args(argv=None) -> ServerConfig:
    d = ServerConfig()
    ap = argparse.ArgumentParser(prog="python -m server",
                                 description="Servidor do SD Chat (TCP/TLS + threads + painel web)")
    ap.add_argument("--host", default=os.environ.get("CHAT_HOST", d.host),
                    help="endereço de escuta (use 0.0.0.0 para aceitar outras máquinas)")
    ap.add_argument("--tls-port", type=int, default=d.tls_port, help="porta TLS (0 desativa)")
    ap.add_argument("--plain-port", type=int, default=d.plain_port, help="porta TCP sem criptografia (0 desativa)")
    ap.add_argument("--dashboard-port", type=int, default=d.dashboard_port, help="porta do painel web")
    ap.add_argument("--cert", default=str(d.cert), help="certificado do servidor (PEM)")
    ap.add_argument("--key", default=str(d.key), help="chave privada do servidor (PEM)")
    ap.add_argument("--bot-token", default=os.environ.get("CHAT_BOT_TOKEN", d.bot_token),
                    help="token que o bot precisa apresentar no HELLO")
    ap.add_argument("--bot-name", default=d.bot_name, help="nome do bot padrão (para avisar quando estiver offline)")
    ap.add_argument("--request-timeout", type=float, default=d.request_timeout,
                    help="tempo limite (s) para o bot responder uma solicitação")
    ap.add_argument("--idle-timeout", type=float, default=d.idle_timeout,
                    help="desconecta clientes sem tráfego por este tempo (s)")
    ap.add_argument("--no-browser", action="store_true", help="não abrir o painel automaticamente")
    a = ap.parse_args(argv)
    return ServerConfig(
        host=a.host, tls_port=a.tls_port, plain_port=a.plain_port, dashboard_port=a.dashboard_port,
        cert=Path(a.cert), key=Path(a.key), bot_token=a.bot_token, bot_name=a.bot_name,
        request_timeout=a.request_timeout, idle_timeout=a.idle_timeout, open_browser=not a.no_browser,
        keylog_file=os.environ.get("SSLKEYLOGFILE") or None,
    )


def build_ssl_context(config: ServerConfig):
    if not config.tls_port:
        return None
    try:
        ctx = tls.server_context(config.cert, config.key, keylog_file=config.keylog_file)
    except tls.TLSConfigError as exc:
        sys.exit(f"[ERRO] {exc}.\n       Gere os certificados com: python certs/gen_certs.py")
    if config.keylog_file:
        # Só para o relatório: permite ao Wireshark decifrar a captura.
        log.warning("SSLKEYLOGFILE ativo: chaves de sessão TLS gravadas em %s (use só em testes)",
                    config.keylog_file)
    return ctx


def main(argv=None) -> int:
    setup_logging(thread_width=18)
    threading.current_thread().name = "principal"
    config = parse_args(argv)
    try:
        config.validate()
    except ValueError as exc:
        sys.exit(f"[ERRO] {exc}")

    server = ChatServer(config, build_ssl_context(config))
    try:
        server.start()
    except ListenerError as exc:
        sys.exit(f"[ERRO] {exc}")
    dashboard = DashboardServer(server, server.monitor.feed, config.dashboard_port)
    dashboard.start(open_browser=config.open_browser)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Encerrando servidor...")
    finally:
        server.stop()
        dashboard.stop()
    return 0
