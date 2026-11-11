"""Regras de validação do servidor: nomes, HELLO e menções a bots.

Funções puras (sem sockets nem estado), fáceis de testar isoladamente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from common import protocol as P
from common.protocol import ErrorCode

_NAME_CHARS = r"[A-Za-z0-9À-ÖØ-öø-ÿ_.\-]"
NAME_RE = re.compile(rf"^{_NAME_CHARS}{{2,20}}$")
MENTION_RE = re.compile(rf"^\s*@({_NAME_CHARS}+)[\s,:]*(.*)$", re.DOTALL)
RESERVED_NAMES = frozenset({"server", "servidor", "todos", "all", "admin", "*"})
CLIENT_INFO_MAX = 60


class RejectConnection(Exception):
    """HELLO recusado (nome inválido/duplicado, token de bot errado...)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Identity:
    """Quem é o participante, segundo o HELLO já validado."""

    name: str
    role: str
    client: str = ""

    @property
    def key(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Mention:
    """Texto que começa com @nome: o nome mencionado e o restante."""

    name: str
    text: str

    def targets(self, name: str) -> bool:
        return self.name.lower() == name.lower()


def is_valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name)) and name.lower() not in RESERVED_NAMES


def validate_hello(hello: dict, bot_token: str) -> Identity:
    """Valida o primeiro quadro da conexão e devolve a identidade declarada."""
    if hello.get("type") != P.HELLO:
        raise RejectConnection(ErrorCode.HELLO_REQUIRED, "o primeiro quadro deve ser HELLO")
    name = str(hello.get("from") or "").strip()
    info = hello.get("content") if isinstance(hello.get("content"), dict) else {}
    role = info.get("role", P.ROLE_HUMAN)
    if role not in P.ROLES:
        raise RejectConnection(ErrorCode.BAD_ROLE, "papel inválido (use 'human' ou 'bot')")
    if not is_valid_name(name):
        raise RejectConnection(ErrorCode.BAD_NAME,
                               "nome inválido: use de 2 a 20 letras, números, '.', '_' ou '-'")
    if role == P.ROLE_BOT and info.get("token") != bot_token:
        raise RejectConnection(ErrorCode.BAD_TOKEN, "token de bot inválido")
    return Identity(name=name, role=role, client=str(info.get("client", ""))[:CLIENT_INFO_MAX])


def parse_mention(text: str) -> Mention | None:
    match = MENTION_RE.match(text)
    return Mention(match.group(1), match.group(2)) if match else None
