"""Acesso à LLM.

O restante do bot depende só da abstração ChatModel; OllamaClient é a
implementação concreta (HTTP com streaming). Trocar de provedor ou usar um
modelo falso nos testes não exige mudar o Assistant (inversão de dependência).
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Protocol

from .errors import Cancelled, LLMTimeout, LLMUnavailable

DeltaCallback = Callable[[str], None]
CHECK_TIMEOUT = 5.0
CONTEXT_TOKENS = 4096


class ChatModel(Protocol):
    model: str
    timeout: float      # inatividade máxima (primeiro token ou entre tokens)
    max_time: float     # duração máxima da resposta completa

    def check(self) -> str:
        """'' se o modelo está pronto; senão, a descrição do problema."""

    def chat_stream(self, messages: list[dict], on_delta: DeltaCallback, cancel: threading.Event) -> str:
        """Gera a resposta chamando on_delta a cada pedaço e devolve o texto completo."""


class OllamaClient:
    def __init__(self, base_url: str, model: str, *, timeout: float, max_time: float,
                 temperature: float, max_tokens: int):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_time = max_time
        self.temperature = temperature
        self.max_tokens = max_tokens

    def check(self) -> str:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=CHECK_TIMEOUT) as resp:
                models = [m.get("name") for m in json.load(resp).get("models", [])]
        except Exception as exc:  # noqa: BLE001 - só diagnóstico
            return f"Ollama inacessível em {self.base_url} ({exc})"
        if self.model not in models:
            return f"modelo '{self.model}' não encontrado no Ollama (instale com: ollama pull {self.model})"
        return ""

    def _request(self, messages: list[dict]) -> urllib.request.Request:
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": True,
            "think": False,              # desliga o "raciocínio" do Qwen: respostas mais rápidas
            "keep_alive": "30m",
            "options": {"temperature": self.temperature, "num_predict": self.max_tokens,
                        "num_ctx": CONTEXT_TOKENS},
        }).encode()
        return urllib.request.Request(f"{self.base_url}/api/chat", data=body,
                                      headers={"Content-Type": "application/json"})

    def chat_stream(self, messages: list[dict], on_delta: DeltaCallback, cancel: threading.Event) -> str:
        """Lança LLMTimeout (inatividade ou duração máxima), LLMUnavailable
        (serviço/modelo indisponível) ou Cancelled (cancel acionado)."""
        timeout = self.timeout
        deadline = time.monotonic() + self.max_time
        parts: list[str] = []
        try:
            # O timeout do urlopen vale para cada leitura do socket HTTP
            # (detecta LLM travada); o prazo total é conferido a cada pedaço.
            with urllib.request.urlopen(self._request(messages), timeout=timeout) as resp:
                for raw in resp:
                    if cancel.is_set():
                        raise Cancelled()
                    if time.monotonic() > deadline:
                        raise LLMTimeout(f"a resposta passou do tempo máximo de {self.max_time:g} s")
                    if not raw.strip():
                        continue
                    chunk = json.loads(raw)
                    if chunk.get("error"):
                        raise LLMUnavailable(chunk["error"])
                    delta = (chunk.get("message") or {}).get("content") or ""
                    if delta:
                        parts.append(delta)
                        on_delta(delta)
                    if chunk.get("done"):
                        break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            raise LLMUnavailable(f"Ollama respondeu HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise LLMTimeout(f"a LLM não respondeu em {timeout:g} s") from exc
            raise LLMUnavailable(f"não foi possível acessar o Ollama em {self.base_url} ({exc.reason})") from exc
        except (socket.timeout, TimeoutError) as exc:
            raise LLMTimeout(f"a LLM ficou {timeout:g} s sem enviar dados") from exc
        except (ConnectionError, OSError) as exc:
            raise LLMUnavailable(f"conexão com o Ollama falhou ({exc})") from exc
        answer = "".join(parts).strip()
        if not answer:
            raise LLMUnavailable("a LLM devolveu uma resposta vazia")
        return answer
