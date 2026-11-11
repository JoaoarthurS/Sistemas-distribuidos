"""Conexão do bot com o servidor: socket TCP/TLS, apresentação e envio seguro."""

from __future__ import annotations

import logging
import socket
import ssl
import threading
from pathlib import Path

from common import protocol as P
from common.transport import SafeSocket

from .errors import HandshakeRejected

log = logging.getLogger("bot")

CONNECT_TIMEOUT = 10.0


class BotConnection:
    """Um socket aberto com o servidor.

    Várias threads enviam (pool de workers, heartbeat) enquanto uma lê:
    o lock de envio impede que dois quadros se intercalem no fluxo e o
    SafeSocket serializa o acesso ao objeto SSL.
    """

    def __init__(self, host: str, port: int, ssl_context: ssl.SSLContext | None,
                 ca_label: str = "", connect_timeout: float = CONNECT_TIMEOUT):
        self.host = host
        self.port = port
        self._ssl_context = ssl_context
        self._ca_label = ca_label
        self._connect_timeout = connect_timeout
        self._send_lock = threading.Lock()
        self._sock: SafeSocket | None = None
        self._reader: P.FrameReader | None = None

    @property
    def secure(self) -> bool:
        return self._ssl_context is not None

    def open(self) -> None:
        raw = socket.create_connection((self.host, self.port), timeout=self._connect_timeout)
        if self.secure:
            # O bot valida o certificado do servidor usando a CA de teste.
            sock = self._ssl_context.wrap_socket(raw, server_hostname=self.host)
            log.info("TLS estabelecido: %s, %s (certificado validado pela CA %s)",
                     sock.version(), sock.cipher()[0], self._ca_label)
        else:
            sock = raw
            log.warning("Conexão SEM criptografia (modo --plain)")
        self._sock = SafeSocket(sock, timeout=None)
        self._reader = P.FrameReader(self._sock)

    def handshake(self, hello: dict) -> dict:
        """Envia HELLO e devolve o WELCOME; lança HandshakeRejected se recusado."""
        self.send(hello)
        welcome = self.read_frame()
        if not welcome or welcome.get("type") != P.WELCOME:
            reason = (welcome or {}).get("content") or "conexão fechada"
            raise HandshakeRejected(f"servidor recusou o bot: {reason}")
        return welcome

    def read_frame(self) -> dict | None:
        return self._reader.read_frame()

    def send(self, frame: dict) -> bool:
        data = P.encode(frame)
        with self._send_lock:
            if self._sock is None:
                return False
            try:
                self._sock.sendall(data)
                return True
            except OSError as exc:
                log.warning("falha ao enviar %s: %s", frame.get("type"), exc)
                return False

    def close(self, goodbye: dict | None = None) -> None:
        """Fecha o socket; com goodbye, envia esse quadro (BYE) antes."""
        with self._send_lock:
            sock, self._sock = self._sock, None
            if sock is None:
                return
            try:
                if goodbye is not None:
                    sock.sendall(P.encode(goodbye))
            except OSError:
                pass
            finally:
                sock.close()


def ca_label(ca: Path | None) -> str:
    return Path(ca).name if ca else "do sistema"
