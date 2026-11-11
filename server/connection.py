"""Conexão de um participante: uma thread leitora e uma escritora por socket.

A ClientConnection só sabe transportar quadros. O que fazer com eles é
decidido por um ConnectionHandler (inversão de dependência): a conexão não
conhece o roteamento, o registro de usuários nem o bot.
"""

from __future__ import annotations

import itertools
import logging
import queue
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from common import protocol as P
from common.protocol import ErrorCode
from common.transport import SafeSocket

from .monitor import Monitor
from .validation import Identity, RejectConnection

log = logging.getLogger("server")

_CLOSE = object()  # sentinela que encerra a thread escritora


class ConnectionHandler(Protocol):
    """O que a conexão notifica ao servidor."""

    def on_hello(self, conn: "ClientConnection", hello: dict) -> None:
        """Valida e registra o participante; lança RejectConnection para recusar."""

    def on_frame(self, conn: "ClientConnection", frame: dict) -> None:
        """Quadro recebido de um participante já identificado."""

    def on_closed(self, conn: "ClientConnection", reason: str, registered: bool) -> None:
        """A conexão terminou (chamado uma única vez, pela thread leitora)."""


@dataclass(frozen=True)
class ConnectionSettings:
    handshake_timeout: float = 10.0
    idle_timeout: float = 90.0
    queue_max: int = 2000
    close_grace: float = 3.0     # s para a escritora esvaziar a fila antes do fechamento forçado


class ClientConnection:
    _ids = itertools.count(1)

    def __init__(self, sock: socket.socket, addr, *, secure: bool, handler: ConnectionHandler,
                 monitor: Monitor, settings: ConnectionSettings,
                 ssl_context: ssl.SSLContext | None = None):
        if secure and ssl_context is None:
            raise ValueError("conexão segura exige um contexto TLS")
        self.cid = next(self._ids)
        self.sock = sock
        self.addr = addr
        self.secure = secure
        self.tls: dict | None = None
        self.name: str | None = None
        self.role: str | None = None
        self.client_info = ""
        self.connected_at = time.time()
        self.last_seen = time.time()
        self.frames_in = 0
        self.frames_out = 0
        self.bytes_out = 0
        self.closed = threading.Event()
        self._handler = handler
        self._monitor = monitor
        self._settings = settings
        self._ssl_context = ssl_context
        self._outq: queue.Queue = queue.Queue(maxsize=settings.queue_max)
        self._reader: P.FrameReader | None = None
        self._reader_thread: threading.Thread | None = None
        self._writer_thread: threading.Thread | None = None

    # ---- identidade --------------------------------------------------------
    @property
    def label(self) -> str:
        return self.name or f"conexão #{self.cid}"

    @property
    def address(self) -> str:
        return f"{self.addr[0]}:{self.addr[1]}"

    @property
    def is_human(self) -> bool:
        return self.role == P.ROLE_HUMAN

    @property
    def is_bot(self) -> bool:
        return self.role == P.ROLE_BOT

    def identify(self, identity: Identity) -> None:
        self.name, self.role, self.client_info = identity.name, identity.role, identity.client

    def public_info(self) -> dict:
        """Dados do participante visíveis aos demais (USER_JOINED/USER_LIST)."""
        return {"name": self.name, "role": self.role, "secure": self.secure, "client": self.client_info}

    # ---- ciclo de vida -------------------------------------------------------
    def start(self) -> None:
        self._reader_thread = threading.Thread(
            target=self._run_reader, name=f"leitor-#{self.cid}", daemon=True)
        self._reader_thread.start()

    def _run_reader(self) -> None:
        registered = False
        try:
            self._handshake()
            self._start_writer()
            self._identify()
            registered = True
            reason = self._read_until_closed()
        except Exception as exc:  # noqa: BLE001 - toda falha vira um motivo de saída
            reason = self._disconnect_reason(exc, registered)
        finally:
            self._handler.on_closed(self, reason, registered)
            self.close()

    def _handshake(self) -> None:
        self.sock.settimeout(self._settings.handshake_timeout)
        if self.secure:
            # O handshake acontece na thread da conexão, não na que aceita
            # conexões: um cliente lento não atrasa os demais.
            self.sock = self._ssl_context.wrap_socket(self.sock, server_side=True)
            cipher = self.sock.cipher()
            self.tls = {"version": self.sock.version(), "cipher": cipher[0], "bits": cipher[2]}
            self._monitor.event("tls", f"Handshake TLS concluído com {self.address}: "
                                       f"{self.tls['version']} / {self.tls['cipher']}")
        # A partir daqui leitora e escritora compartilham o socket: SafeSocket
        # serializa o acesso ao objeto SSL (ver common/transport.py).
        self.sock = SafeSocket(self.sock, timeout=self._settings.handshake_timeout)
        self._reader = P.FrameReader(self.sock)

    def _start_writer(self) -> None:
        self._writer_thread = threading.Thread(
            target=self._run_writer, name=f"escritor-#{self.cid}", daemon=True)
        self._writer_thread.start()

    def _identify(self) -> None:
        hello = self._reader.read_frame()
        if hello is None:
            raise RejectConnection(ErrorCode.HELLO_REQUIRED, "conexão fechada antes do HELLO")
        self.frames_in += 1
        self._handler.on_hello(self, hello)
        threading.current_thread().name = f"leitor-{self.name}"
        self._writer_thread.name = f"escritor-{self.name}"

    def _read_until_closed(self) -> str:
        self.sock.settimeout(self._settings.idle_timeout)
        while not self.closed.is_set():
            try:
                frame = self._reader.read_frame()
            except P.FrameTooLarge:
                raise
            except P.ProtocolError as exc:
                self.send(P.make(P.ERROR, to=self.name, content=str(exc), code=ErrorCode.BAD_FRAME))
                continue
            if frame is None:
                return "cliente fechou a conexão"
            self.frames_in += 1
            self.last_seen = time.time()
            if frame.get("type") == P.BYE:
                return "saiu do chat"
            self._handler.on_frame(self, frame)
        return "conexão encerrada"

    def _disconnect_reason(self, exc: BaseException, registered: bool) -> str:
        """Traduz a exceção que encerrou a leitura em um motivo legível."""
        lost = self.closed.is_set()  # fechada por nós (kick, fila cheia, desligamento)
        if isinstance(exc, RejectConnection):
            return f"HELLO recusado: {exc}"
        if isinstance(exc, socket.timeout):
            return "tempo de inatividade excedido" if registered else "tempo limite no handshake"
        if isinstance(exc, ssl.SSLError):
            return f"falha TLS: {exc.reason or exc}"
        if isinstance(exc, P.FrameTooLarge):
            return f"quadro grande demais ({exc})"
        if isinstance(exc, ConnectionResetError):
            return "conexão perdida" if lost else "conexão interrompida sem aviso (sem BYE)"
        if isinstance(exc, ConnectionAbortedError):
            return "conexão perdida" if lost else "conexão abortada"
        if isinstance(exc, OSError):
            return "conexão perdida" if lost else f"falha de conexão: {exc}"
        log.error("erro na conexão %s", self.label, exc_info=exc)
        return f"erro interno: {exc}"

    def _run_writer(self) -> None:
        try:
            while True:
                item = self._outq.get()
                if item is _CLOSE:
                    break
                data = P.encode(item)
                self.sock.sendall(data)
                self.frames_out += 1
                self.bytes_out += len(data)
        except (OSError, P.ProtocolError):
            pass
        finally:
            self.closed.set()
            self._shutdown_socket()

    # ---- envio e fechamento --------------------------------------------------
    def send(self, frame: dict) -> bool:
        """Enfileira um quadro para a thread escritora (nunca bloqueia)."""
        if self.closed.is_set():
            return False
        try:
            self._outq.put_nowait(frame)
            return True
        except queue.Full:
            self._monitor.event("error", f"{self.label} não está consumindo mensagens; conexão encerrada")
            self.close(force=True)
            return False

    def close(self, force: bool = False) -> None:
        """Fecha a conexão depois de enviar o que já estava na fila."""
        if self.closed.is_set() and not force:
            return
        self.closed.set()
        if force or self._writer_thread is None:
            self._shutdown_socket()
            return
        try:
            self._outq.put_nowait(_CLOSE)
        except queue.Full:
            self._shutdown_socket()
        # garantia: se a escritora estiver presa num envio, força o fechamento
        timer = threading.Timer(self._settings.close_grace, self._shutdown_socket)
        timer.daemon = True
        timer.start()

    def _shutdown_socket(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    # ---- painel ----------------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "cid": self.cid,
            "name": self.name,
            "role": self.role or "pendente",
            "address": self.address,
            "secure": self.secure,
            "tls": self.tls,
            "client": self.client_info,
            "connected_at": int(self.connected_at * 1000),
            "last_seen": int(self.last_seen * 1000),
            "frames_in": self.frames_in,
            "frames_out": self.frames_out,
            "bytes_in": self._reader.bytes_read if self._reader else 0,
            "bytes_out": self.bytes_out,
            "queue": self._outq.qsize(),
            "threads": [t.name for t in (self._reader_thread, self._writer_thread) if t and t.is_alive()],
        }
