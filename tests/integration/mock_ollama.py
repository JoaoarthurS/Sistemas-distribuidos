"""
Servidor HTTP que imita a API /api/chat do Ollama (streaming NDJSON).
Usado só nos testes automatizados, para ter respostas determinísticas:

- a resposta informa quantos turnos anteriores vieram no contexto e quais
  foram as perguntas anteriores (permite verificar histórico por usuário);
- se a pergunta contiver "[lento]", espera antes de responder (timeout).
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    slow_seconds = 8.0
    word_delay = 0.08

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps({"models": [{"name": "mock"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = req["messages"]
        question = msgs[-1]["content"]
        previous = [m["content"] for m in msgs[1:-1] if m["role"] == "user"]
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        if "[lento]" in question:
            time.sleep(self.slow_seconds)
        text = (f"turnos anteriores: {len(previous)} | anteriores={previous} | "
                f"pergunta={question} | resposta simulada com varias palavras para testar streaming")
        try:
            for word in text.split(" "):
                self._chunk({"message": {"role": "assistant", "content": word + " "}, "done": False})
                time.sleep(self.word_delay)
            self._chunk({"message": {"role": "assistant", "content": ""}, "done": True})
            self.wfile.write(b"0\r\n\r\n")
        except OSError:
            pass  # cliente (bot) desistiu

    def _chunk(self, obj):
        data = (json.dumps(obj) + "\n").encode()
        self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()


def start(port: int = 0) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, name="mock-ollama", daemon=True).start()
    return httpd
