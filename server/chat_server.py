"""ChatServer: compõe registro, sessões, roteador e broker e controla o ciclo de vida.

Implementa duas interfaces pequenas:
- ConnectionHandler (connection.py): recebe os eventos de cada conexão e
  delega a quem tem a responsabilidade (SessionManager ou MessageRouter);
- AdminService (dashboard/handler.py): o que o painel pode consultar e fazer.
"""

from __future__ import annotations

import socket
import ssl
import threading
import time

from common import protocol as P
from common.protocol import ErrorCode

from .bot_broker import BotBroker
from .config import ServerConfig
from .connection import ClientConnection, ConnectionSettings
from .listener import TcpListener
from .monitor import Monitor
from .registry import ClientRegistry
from .router import MessageRouter
from .sessions import SessionManager

WATCHDOG_INTERVAL = 0.5   # s entre verificações de solicitações expiradas
SHUTDOWN_GRACE = 0.5      # s para as escritoras enviarem o aviso de desligamento


class ChatServer:
    def __init__(self, config: ServerConfig, ssl_context: ssl.SSLContext | None = None,
                 monitor: Monitor | None = None):
        if config.tls_port and ssl_context is None:
            raise ValueError("a porta TLS exige um contexto TLS (common.tls.server_context)")
        self.config = config
        self.monitor = monitor or Monitor()
        self.registry = ClientRegistry()
        self.broker = BotBroker(self.registry, self.monitor, request_timeout=config.request_timeout,
                                max_pending_per_user=config.max_pending_per_user)
        self.sessions = SessionManager(self.registry, self.broker, self.monitor, config)
        self.router = MessageRouter(self.registry, self.broker, self.monitor, bot_name=config.bot_name)
        self.started_at = time.time()
        self._ssl_context = ssl_context
        self._settings = ConnectionSettings(handshake_timeout=config.handshake_timeout,
                                            idle_timeout=config.idle_timeout,
                                            queue_max=config.outbound_queue_max)
        self._listeners: list[TcpListener] = []
        self._running = threading.Event()

    # ---- ConnectionHandler ---------------------------------------------------------
    def on_hello(self, conn: ClientConnection, hello: dict) -> None:
        self.sessions.join(conn, hello)

    def on_frame(self, conn: ClientConnection, frame: dict) -> None:
        self.router.route(conn, frame)

    def on_closed(self, conn: ClientConnection, reason: str, registered: bool) -> None:
        self.sessions.leave(conn, reason, registered)

    # ---- ciclo de vida ------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._running.is_set()

    def start(self) -> None:
        """Abre as portas e inicia as threads de aceitação e o watchdog.

        Lança listener.ListenerError se alguma porta estiver ocupada.
        """
        self._running.set()
        endpoints = [(self.config.plain_port, False), (self.config.tls_port, True)]
        for port, secure in endpoints:
            if port:
                listener = TcpListener(self.config.host, port, secure=secure, on_accept=self._accept)
                listener.start()
                self._listeners.append(listener)
        threading.Thread(target=self._watchdog_loop, name="watchdog-bot", daemon=True).start()
        ports = [f"{'TLS' if lst.secure else 'TCP puro'} {lst.host}:{lst.port}"
                 for lst in sorted(self._listeners, key=lambda lst: not lst.secure)]
        self.monitor.event("server", "Servidor iniciado — " + " | ".join(ports))

    def stop(self) -> None:
        self._running.clear()
        for listener in self._listeners:
            listener.close()
        self.registry.broadcast(P.make(P.SYSTEM, content="O servidor está sendo encerrado.",
                                       code=ErrorCode.SHUTDOWN))
        for conn in self.registry.connections():
            conn.close()
        time.sleep(SHUTDOWN_GRACE)

    def _accept(self, sock: socket.socket, addr, secure: bool) -> None:
        conn = ClientConnection(sock, addr, secure=secure, handler=self, monitor=self.monitor,
                                settings=self._settings, ssl_context=self._ssl_context if secure else None)
        self.registry.track(conn)
        self.monitor.count("connections_total")
        self.monitor.event("connect", f"Nova conexão {'TLS' if secure else 'TCP'} de {addr[0]}:{addr[1]}")
        conn.start()

    def _watchdog_loop(self) -> None:
        while self._running.is_set():
            time.sleep(WATCHDOG_INTERVAL)
            self.broker.expire_overdue()

    # ---- AdminService (painel) ----------------------------------------------------
    def snapshot(self) -> dict:
        threads = sorted(({"name": t.name, "daemon": t.daemon} for t in threading.enumerate()),
                         key=lambda t: t["name"])
        return {
            "uptime": round(time.time() - self.started_at),
            "host": self.config.host,
            "plain_port": self.config.plain_port,
            "tls_port": self.config.tls_port,
            "request_timeout": self.config.request_timeout,
            "idle_timeout": self.config.idle_timeout,
            "clients": [c.snapshot() for c in self.registry.connections()],
            "pending": self.broker.snapshot(),
            "stats": self.monitor.stats.snapshot(),
            "threads": threads,
        }

    def broadcast_notice(self, text: str) -> int:
        n = self.registry.broadcast(P.make(P.SYSTEM, content=text), humans_only=True)
        self.monitor.record("system", "servidor", "todos", text)
        self.monitor.event("admin", f"Aviso enviado a {n} participante(s): {text}")
        return n

    def kick(self, name: str) -> bool:
        conn = self.registry.get(name)
        if not conn:
            return False
        conn.send(P.make(P.SYSTEM, to=conn.name, content="Você foi desconectado pelo administrador.",
                         code=ErrorCode.KICKED))
        self.monitor.event("admin", f"Administrador desconectou {conn.name}")
        conn.close()
        return True
