"""Servidor HTTP do painel: arquivos estáticos, API JSON e Server-Sent Events.

O painel depende apenas da interface AdminService (o que ele pode consultar
e fazer) e do ActivityFeed — não conhece sockets, threads nem o roteamento.
"""

from __future__ import annotations

import itertools
import json
import logging
import queue
import threading
import time
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlsplit

from ..monitor import ActivityFeed

log = logging.getLogger("server")

STATIC_DIR = Path(__file__).resolve().parent / "static"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}
MAX_BODY_BYTES = 10_000
BROADCAST_MAX_CHARS = 500
STATE_INTERVAL = 1.0      # s entre snapshots enviados pelo SSE
SSE_POLL = 0.5            # s de espera por novos itens do feed


class AdminService(Protocol):
    """Operações que o painel pode executar no servidor de chat."""

    @property
    def running(self) -> bool: ...

    def snapshot(self) -> dict: ...

    def broadcast_notice(self, text: str) -> int: ...

    def kick(self, name: str) -> bool: ...


class DashboardHandler(BaseHTTPRequestHandler):
    _sse_ids = itertools.count(1)

    def __init__(self, *args, service: AdminService, feed: ActivityFeed, static_dir: Path = STATIC_DIR,
                 **kwargs):
        self.service = service
        self.feed = feed
        self.static_dir = static_dir.resolve()
        self._get_routes = {"/api/state": self._api_state, "/api/stream": self._api_stream}
        self._post_routes = {"/api/broadcast": self._api_broadcast, "/api/kick": self._api_kick}
        super().__init__(*args, **kwargs)

    def log_message(self, fmt, *args):  # silencia o log padrão do http.server
        pass

    # ---- roteamento HTTP --------------------------------------------------------------
    def do_GET(self):
        path = urlsplit(self.path).path
        route = self._get_routes.get(path)
        if route:
            route()
        else:
            self._static(path)

    def do_POST(self):
        # Exigir JSON impede que outra página dispare ações via formulário (CSRF).
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._json({"ok": False, "error": "use Content-Type: application/json"}, 415)
        route = self._post_routes.get(urlsplit(self.path).path)
        if route is None:
            return self.send_error(404)
        length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY_BYTES)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"ok": False, "error": "JSON inválido"}, 400)
        if not isinstance(data, dict):
            return self._json({"ok": False, "error": "esperado um objeto JSON"}, 400)
        route(data)

    # ---- arquivos estáticos -------------------------------------------------------------
    def _resolve_static(self, url_path: str) -> Path | None:
        relative = unquote(url_path).lstrip("/") or "index.html"
        candidate = (self.static_dir / relative).resolve()
        # impede path traversal (ex.: /../../certs/server.key)
        if not candidate.is_relative_to(self.static_dir) or not candidate.is_file():
            return None
        return candidate

    def _static(self, url_path: str) -> None:
        file = self._resolve_static(url_path)
        if file is None:
            return self.send_error(404)
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(file.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---- API ------------------------------------------------------------------------------
    def _full_state(self) -> dict:
        return {**self.service.snapshot(), **self.feed.recent()}

    def _api_state(self) -> None:
        self._json(self._full_state())

    def _api_broadcast(self, data: dict) -> None:
        text = str(data.get("text", "")).strip()[:BROADCAST_MAX_CHARS]
        if not text:
            return self._json({"ok": False, "error": "texto vazio"}, 400)
        self._json({"ok": True, "recipients": self.service.broadcast_notice(text)})

    def _api_kick(self, data: dict) -> None:
        ok = self.service.kick(str(data.get("name", "")))
        self._json({"ok": ok}, 200 if ok else 404)

    def _api_stream(self) -> None:
        """SSE: envia 'init', depois 'event'/'message' em tempo real e 'state' a cada segundo."""
        threading.current_thread().name = f"painel-sse-{next(self._sse_ids)}"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        q = self.feed.subscribe()
        try:
            self._sse("init", self._full_state())
            last = time.monotonic()
            while self.service.running:
                try:
                    kind, item = q.get(timeout=SSE_POLL)
                    self._sse(kind, item)
                except queue.Empty:
                    pass
                if time.monotonic() - last >= STATE_INTERVAL:
                    self._sse("state", self.service.snapshot())
                    last = time.monotonic()
        except OSError:
            pass  # navegador fechou a aba
        finally:
            self.feed.unsubscribe(q)

    # ---- respostas ------------------------------------------------------------------------
    def _json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, kind: str, data) -> None:
        payload = json.dumps(data, ensure_ascii=False)
        self.wfile.write(f"event: {kind}\ndata: {payload}\n\n".encode())
        self.wfile.flush()


class DashboardServer:
    """Sobe o painel em 127.0.0.1 numa thread própria."""

    def __init__(self, service: AdminService, feed: ActivityFeed, port: int, host: str = "127.0.0.1"):
        self.host = host
        self.port = port
        self._handler = partial(DashboardHandler, service=service, feed=feed)
        self._httpd: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self, open_browser: bool = False) -> bool:
        try:
            self._httpd = ThreadingHTTPServer((self.host, self.port), self._handler)
        except OSError as exc:
            log.warning("painel indisponível na porta %s: %s", self.port, exc)
            return False
        self._httpd.daemon_threads = True
        threading.Thread(target=self._httpd.serve_forever, name="painel-http", daemon=True).start()
        log.info("Painel do servidor: %s", self.url)
        if open_browser:
            threading.Timer(0.8, lambda: webbrowser.open(self.url)).start()
        return True

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
