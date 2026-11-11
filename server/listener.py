"""Socket de escuta TCP com uma thread dedicada a aceitar conexões."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable

AcceptCallback = Callable[[socket.socket, tuple, bool], None]


class ListenerError(OSError):
    """Não foi possível abrir a porta de escuta."""


class TcpListener:
    def __init__(self, host: str, port: int, *, secure: bool, on_accept: AcceptCallback, backlog: int = 64):
        self.host = host
        self.port = port
        self.secure = secure
        self._on_accept = on_accept
        self._backlog = backlog
        self._sock: socket.socket | None = None
        self._running = threading.Event()

    @property
    def thread_name(self) -> str:
        return f"aceita-{'tls' if self.secure else 'tcp'}:{self.port}"

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.host, self.port))
        except OSError as exc:
            sock.close()
            raise ListenerError(f"não foi possível usar a porta {self.port}: {exc}") from exc
        sock.listen(self._backlog)
        self._sock = sock
        self._running.set()
        threading.Thread(target=self._accept_loop, name=self.thread_name, daemon=True).start()

    def _accept_loop(self) -> None:
        # O accept() fica nesta thread: o tratamento de cada cliente (inclusive
        # o handshake TLS) acontece nas threads da própria conexão.
        while self._running.is_set():
            try:
                client, addr = self._sock.accept()
            except OSError:
                break
            self._on_accept(client, addr, self.secure)

    def close(self) -> None:
        self._running.clear()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
