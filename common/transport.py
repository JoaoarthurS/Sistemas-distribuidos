"""
Socket seguro para uso por várias threads (TCP puro ou TLS).

Problema: no servidor e no bot, uma thread fica lendo do socket enquanto
outras escrevem nele. Com TLS isso é perigoso: o OpenSSL NÃO permite usar o
mesmo objeto SSL em duas threads ao mesmo tempo (ex.: a leitora processando
um NewSessionTicket do TLS 1.3 enquanto outra thread cifra um registro).
Nos testes isso derrubava ~3% das conexões.

Solução: o socket fica em modo não bloqueante e toda chamada recv()/send()
acontece com um lock adquirido — e como a chamada não bloqueia, o lock fica
preso só por microssegundos. A espera por dados (ou por espaço no buffer de
envio) acontece FORA do lock, com select(). Assim a leitora pode aguardar
indefinidamente sem impedir que outras threads enviem.
"""

from __future__ import annotations

import select
import socket
import ssl
import threading
import time

_WAIT_SLICE = 0.5  # s: acorda periodicamente para perceber fechamento do socket


class SafeSocket:
    def __init__(self, sock: socket.socket, timeout: float | None = None, send_timeout: float = 30.0):
        self.sock = sock
        self.timeout = timeout            # inatividade máxima na leitura (None = sem limite)
        self.send_timeout = send_timeout  # tempo máximo esperando o par consumir dados
        self._lock = threading.Lock()
        self._closed = False
        sock.setblocking(False)

    # mantém a mesma interface de socket usada pelo restante do código
    def settimeout(self, timeout: float | None) -> None:
        self.timeout = timeout

    def _wait(self, want: str, timeout: float) -> None:
        if self._closed:
            raise ConnectionAbortedError("socket fechado localmente")
        try:
            if want == "r":
                select.select([self.sock], [], [], timeout)
            else:
                select.select([], [self.sock], [], timeout)
        except (ValueError, OSError) as exc:  # socket fechado por outra thread
            raise ConnectionAbortedError("socket fechado localmente") from exc

    def recv(self, size: int) -> bytes:
        deadline = None if self.timeout is None else time.monotonic() + self.timeout
        while True:
            with self._lock:
                if self._closed:
                    raise ConnectionAbortedError("socket fechado localmente")
                try:
                    return self.sock.recv(size)
                except (ssl.SSLWantReadError, BlockingIOError):
                    want = "r"
                except ssl.SSLWantWriteError:
                    want = "w"
            # Sempre tenta ler ANTES do select: o OpenSSL pode ter dados já
            # decifrados em buffer interno sem que o socket esteja "legível".
            if deadline is None:
                self._wait(want, _WAIT_SLICE)
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise socket.timeout("tempo de inatividade excedido")
                self._wait(want, min(remaining, _WAIT_SLICE))

    def sendall(self, data: bytes) -> None:
        view = memoryview(data)
        deadline = time.monotonic() + self.send_timeout
        while view:
            with self._lock:
                if self._closed:
                    raise ConnectionAbortedError("socket fechado localmente")
                try:
                    sent = self.sock.send(view)
                    view = view[sent:]
                    continue
                except (ssl.SSLWantWriteError, BlockingIOError):
                    want = "w"
                except ssl.SSLWantReadError:
                    want = "r"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("o destinatário não está consumindo os dados")
            self._wait(want, min(remaining, _WAIT_SLICE))

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass

    def shutdown(self, how: int = socket.SHUT_RDWR) -> None:
        self.close()

    # informações do TLS (None para TCP puro)
    def version(self):
        return self.sock.version() if isinstance(self.sock, ssl.SSLSocket) else None

    def cipher(self):
        return self.sock.cipher() if isinstance(self.sock, ssl.SSLSocket) else None
