"""
Configuração TLS compartilhada pelo servidor, pelo bot e pelos testes.

Centralizar a criação dos contextos garante que todos os componentes usem a
mesma política (versão mínima, validação de certificado) — mudar a política
exige alterar um único lugar.
"""

from __future__ import annotations

import ssl
from pathlib import Path

MIN_VERSION = ssl.TLSVersion.TLSv1_2


class TLSConfigError(RuntimeError):
    """Certificado ou chave ausente/inválido."""


def server_context(cert: str | Path, key: str | Path, keylog_file: str | None = None) -> ssl.SSLContext:
    """Contexto do lado servidor com o certificado e a chave informados.

    keylog_file (opcional, só para testes): grava as chaves de sessão para o
    Wireshark conseguir decifrar uma captura, provando que o conteúdo trafega
    cifrado.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = MIN_VERSION
    try:
        ctx.load_cert_chain(str(cert), str(key))
    except (FileNotFoundError, ssl.SSLError) as exc:
        raise TLSConfigError(f"não foi possível carregar o certificado TLS ({exc})") from exc
    if keylog_file:
        ctx.keylog_filename = keylog_file
    return ctx


def client_context(cafile: str | Path | None) -> ssl.SSLContext:
    """Contexto do lado cliente que valida a cadeia e o nome/IP do servidor.

    Com cafile, confia SOMENTE nessa CA (a CA de teste do projeto); com None,
    usa as CAs do sistema operacional.
    """
    ctx = ssl.create_default_context(cafile=str(cafile) if cafile else None)
    ctx.minimum_version = MIN_VERSION
    return ctx
