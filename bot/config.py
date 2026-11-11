"""Parâmetros de execução do bot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CA = PROJECT_ROOT / "certs" / "ca.crt"
TLS_PORT = 5443
PLAIN_PORT = 5000


@dataclass(frozen=True)
class BotConfig:
    host: str = "127.0.0.1"
    port: int = TLS_PORT
    plain: bool = False                  # conecta sem TLS (só para comparação)
    ca: Path = DEFAULT_CA                # CA usada para validar o certificado do servidor
    name: str = "bot"                    # nome no chat (menção @nome)
    token: str = "dev-bot-token"
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3.5:4b"
    llm_timeout: float = 90.0            # s sem receber dados da LLM (inatividade)
    llm_max_time: float = 180.0          # s de duração máxima de uma resposta
    history_turns: int = 4               # turnos (pergunta + resposta) lembrados por usuário
    workers: int = 4                     # threads que processam perguntas em paralelo
    temperature: float = 0.6
    max_tokens: int = 600
    heartbeat_interval: float = 25.0     # s entre PINGs
    reconnect_initial: float = 2.0       # s antes da 1ª tentativa de reconexão
    reconnect_max: float = 30.0          # teto do backoff exponencial

    @property
    def client_id(self) -> str:
        return f"sd-bot/{self.model}"
