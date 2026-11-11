"""Parâmetros de execução do servidor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CERTS_DIR = PROJECT_ROOT / "certs"


@dataclass(frozen=True)
class ServerConfig:
    """Configuração imutável: criada uma vez (cli.py) e compartilhada sem locks."""

    host: str = "127.0.0.1"
    tls_port: int = 5443                 # 0 desativa
    plain_port: int = 5000               # 0 desativa (porta de referência para o Wireshark)
    dashboard_port: int = 8080
    cert: Path = CERTS_DIR / "server.crt"
    key: Path = CERTS_DIR / "server.key"
    bot_token: str = "dev-bot-token"
    bot_name: str = "bot"                # usado para avisar BOT_OFFLINE
    request_timeout: float = 200.0       # s para o bot responder uma solicitação
    idle_timeout: float = 90.0           # s sem tráfego até desconectar o cliente
    open_browser: bool = True
    keylog_file: str | None = None       # SSLKEYLOGFILE (só para testes)
    handshake_timeout: float = 10.0      # s para concluir TLS + HELLO
    outbound_queue_max: int = 2000       # quadros na fila antes de considerar o cliente travado
    max_pending_per_user: int = 3        # perguntas simultâneas ao bot por usuário

    def validate(self) -> None:
        if not self.tls_port and not self.plain_port:
            raise ValueError("habilite ao menos uma porta (TLS ou TCP)")
        if self.request_timeout <= 0 or self.idle_timeout <= 0:
            raise ValueError("os tempos limite devem ser positivos")
