"""
Protocolo de aplicação do SD Chat.

Cada quadro (frame) é um objeto JSON codificado em UTF-8 e terminado por
'\\n' (NDJSON). O JSON escapa quebras de linha dentro de strings, portanto
o byte 0x0A só aparece como delimitador. Campos comuns:

    type     tipo da mensagem (HELLO, MSG, BOT_REQUEST, ...)
    id       identificador único do quadro (gerado pelo remetente)
    from     remetente (o servidor sobrescreve para impedir falsificação)
    to       destinatário: nome do usuário, "*" (todos) ou "server"
    content  conteúdo (texto ou objeto, conforme o tipo)
    req_id   identificador da solicitação ao bot (correlação pedido/resposta)
    ref      id do quadro ao qual este responde (ACK/ERROR)
    ts       instante em milissegundos (epoch)

A especificação completa está em docs/PROTOCOLO.md.
"""

from __future__ import annotations

import json
import time
import uuid

ENCODING = "utf-8"
DELIMITER = b"\n"
MAX_FRAME_BYTES = 64 * 1024      # tamanho máximo de um quadro
MAX_TEXT_CHARS = 4000            # tamanho máximo do texto de uma mensagem
RECV_CHUNK = 8192                # bytes pedidos a cada recv()

BROADCAST = "*"
SERVER = "server"

# Papéis de um participante (campo content.role do HELLO)
ROLE_HUMAN = "human"
ROLE_BOT = "bot"
ROLES = frozenset({ROLE_HUMAN, ROLE_BOT})

# Cliente -> servidor
HELLO = "HELLO"
MSG = "MSG"
TYPING = "TYPING"
LIST = "LIST"
PING = "PING"
BYE = "BYE"

# Servidor -> cliente
WELCOME = "WELCOME"
ACK = "ACK"
PONG = "PONG"
USER_JOINED = "USER_JOINED"
USER_LEFT = "USER_LEFT"
USER_LIST = "USER_LIST"
SYSTEM = "SYSTEM"
ERROR = "ERROR"

# Servidor <-> bot
BOT_REQUEST = "BOT_REQUEST"    # servidor -> bot
BOT_CANCEL = "BOT_CANCEL"      # servidor -> bot (timeout ou usuário saiu)
BOT_TYPING = "BOT_TYPING"      # bot -> servidor -> usuário
BOT_CHUNK = "BOT_CHUNK"        # bot -> servidor -> usuário (streaming)
BOT_RESPONSE = "BOT_RESPONSE"  # bot -> servidor -> usuário (resposta final)
BOT_ERROR = "BOT_ERROR"        # bot/servidor -> usuário (falha ou timeout)

BOT_REPLY_TYPES = frozenset({BOT_TYPING, BOT_CHUNK, BOT_RESPONSE, BOT_ERROR})
BOT_FINAL_TYPES = frozenset({BOT_RESPONSE, BOT_ERROR})


class ErrorCode:
    """Valores do campo 'code' de ERROR, BOT_ERROR e SYSTEM (docs/PROTOCOLO.md, seção 6)."""

    # identificação (HELLO)
    HELLO_REQUIRED = "HELLO_REQUIRED"
    BAD_NAME = "BAD_NAME"
    NAME_TAKEN = "NAME_TAKEN"
    BAD_ROLE = "BAD_ROLE"
    BAD_TOKEN = "BAD_TOKEN"
    # quadros e mensagens
    BAD_FRAME = "BAD_FRAME"
    BAD_TYPE = "BAD_TYPE"
    EMPTY = "EMPTY"
    TOO_LONG = "TOO_LONG"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    TOO_MANY_REQUESTS = "TOO_MANY_REQUESTS"
    # bot
    BOT_OFFLINE = "BOT_OFFLINE"
    TIMEOUT = "TIMEOUT"
    LLM_ERROR = "LLM_ERROR"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    INTERNAL = "INTERNAL"
    # avisos do servidor
    KICKED = "KICKED"
    SHUTDOWN = "SHUTDOWN"


class ProtocolError(Exception):
    """Quadro malformado (JSON inválido ou sem campo 'type')."""


class FrameTooLarge(ProtocolError):
    """Quadro excede MAX_FRAME_BYTES; a conexão deve ser encerrada."""


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now_ms() -> int:
    return int(time.time() * 1000)


def make(type_: str, *, sender: str = SERVER, to: str | None = None,
         content=None, req_id: str | None = None, ref: str | None = None,
         id: str | None = None, **extra) -> dict:
    """Monta um quadro com os campos padrão do protocolo.

    Campos extras com valor None são omitidos (ex.: code, meta).
    """
    frame = {
        "type": type_,
        "id": id or new_id(),
        "from": sender,
        "to": to,
        "content": content,
        "ts": now_ms(),
    }
    if req_id is not None:
        frame["req_id"] = req_id
    if ref is not None:
        frame["ref"] = ref
    frame.update({k: v for k, v in extra.items() if v is not None})
    return frame


def encode(frame: dict) -> bytes:
    """Serializa um quadro: JSON compacto em UTF-8 + delimitador."""
    data = json.dumps(frame, ensure_ascii=False, separators=(",", ":")).encode(ENCODING)
    if len(data) >= MAX_FRAME_BYTES:
        raise FrameTooLarge(f"quadro com {len(data)} bytes")
    return data + DELIMITER


def decode(line: bytes) -> dict:
    """Converte uma linha (sem o delimitador) em quadro, validando o campo 'type'."""
    try:
        obj = json.loads(line.decode(ENCODING))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"JSON inválido: {exc}") from exc
    if not isinstance(obj, dict) or not isinstance(obj.get("type"), str):
        raise ProtocolError("quadro sem campo 'type'")
    return obj


class FrameReader:
    """
    Lê quadros de um socket (TCP ou TLS) tratando a delimitação.

    O TCP é um fluxo de bytes: um recv() pode trazer meio quadro ou vários
    quadros juntos. Os bytes recebidos são acumulados em um buffer e cada
    '\\n' encontrado marca o fim de um quadro completo.
    """

    def __init__(self, sock, max_bytes: int = MAX_FRAME_BYTES):
        self.sock = sock
        self.max_bytes = max_bytes
        self.buffer = bytearray()
        self.bytes_read = 0

    def read_frame(self) -> dict | None:
        """Retorna o próximo quadro ou None quando o par fecha a conexão.

        Lança ProtocolError para JSON inválido (o buffer continua consistente,
        então o chamador pode seguir lendo) e FrameTooLarge para quadros
        acima do limite.
        """
        while True:
            idx = self.buffer.find(DELIMITER)
            if idx >= 0:
                line = bytes(self.buffer[:idx])
                del self.buffer[: idx + 1]
                if not line.strip():
                    continue
                return decode(line)
            if len(self.buffer) > self.max_bytes:
                raise FrameTooLarge(f"mais de {self.max_bytes} bytes sem delimitador")
            chunk = self.sock.recv(RECV_CHUNK)
            if not chunk:
                return None
            self.bytes_read += len(chunk)
            self.buffer += chunk
