"""Exceções do bot. Cada falha da LLM carrega o código enviado no BOT_ERROR."""

from common.protocol import ErrorCode


class LLMError(Exception):
    code = ErrorCode.LLM_ERROR


class LLMTimeout(LLMError):
    code = ErrorCode.LLM_TIMEOUT


class LLMUnavailable(LLMError):
    code = ErrorCode.LLM_UNAVAILABLE


class Cancelled(Exception):
    """A solicitação foi cancelada (BOT_CANCEL, usuário saiu ou conexão caiu)."""


class HandshakeRejected(RuntimeError):
    """O servidor recusou o HELLO do bot."""
