"""Registro thread-safe dos participantes conectados."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import ClientConnection
    from .validation import Identity


class ClientRegistry:
    """Guarda as conexões abertas e o índice nome → conexão.

    Regra de concorrência: o lock protege apenas os dicionários; nenhum envio
    acontece com ele preso (ClientConnection.send só enfileira, então mesmo o
    broadcast é rápido e não bloqueia outras threads).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._by_name: dict[str, ClientConnection] = {}   # nome em minúsculas -> conexão
        self._connections: set[ClientConnection] = set()  # inclui conexões ainda sem HELLO

    # ---- conexões --------------------------------------------------------------
    def track(self, conn: ClientConnection) -> None:
        with self._lock:
            self._connections.add(conn)

    def connections(self) -> list[ClientConnection]:
        with self._lock:
            return sorted(self._connections, key=lambda c: c.cid)

    # ---- participantes identificados ------------------------------------------
    def claim(self, conn: ClientConnection, identity: Identity) -> bool:
        """Registra o nome se estiver livre.

        Verificar e inserir sob o mesmo lock evita que dois clientes
        registrem o mesmo nome ao mesmo tempo (condição de corrida).
        """
        with self._lock:
            if identity.key in self._by_name:
                return False
            conn.identify(identity)
            self._by_name[identity.key] = conn
            return True

    def release(self, conn: ClientConnection) -> bool:
        """Remove a conexão; devolve True se ela era a dona de um nome registrado."""
        with self._lock:
            self._connections.discard(conn)
            key = (conn.name or "").lower()
            if key and self._by_name.get(key) is conn:
                del self._by_name[key]
                return True
            return False

    def get(self, name: str | None) -> ClientConnection | None:
        if not name:
            return None
        with self._lock:
            return self._by_name.get(name.lower())

    def members(self, *, exclude: ClientConnection | None = None,
                humans_only: bool = False) -> list[ClientConnection]:
        with self._lock:
            return [c for c in self._by_name.values()
                    if c is not exclude and (not humans_only or c.is_human)]

    def users(self) -> list[dict]:
        return [c.public_info() for c in self.members()]

    def broadcast(self, frame: dict, *, exclude: ClientConnection | None = None,
                  humans_only: bool = False) -> int:
        """Envia uma cópia do quadro a cada participante; devolve quantos receberam."""
        sent = 0
        for conn in self.members(exclude=exclude, humans_only=humans_only):
            sent += conn.send(dict(frame, to=frame.get("to") or conn.name))
        return sent
