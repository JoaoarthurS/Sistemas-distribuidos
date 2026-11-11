"""ChatBot: mantém a sessão com o servidor e despacha os quadros recebidos.

- Reconecta com backoff exponencial se a conexão cair.
- A thread leitora só despacha: cada BOT_REQUEST vai para um pool de threads,
  então o bot atende vários usuários em paralelo sem bloquear a leitura.
- Todas as respostas usam o mesmo req_id da solicitação.
"""

from __future__ import annotations

import logging
import ssl
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from common import protocol as P
from common.protocol import ErrorCode

from .assistant import Assistant
from .config import BotConfig
from .connection import BotConnection
from .errors import Cancelled, HandshakeRejected, LLMError
from .streaming import ChunkBuffer
from .tracker import BotStats, RequestTracker

log = logging.getLogger("bot")

ConnectionFactory = Callable[[], BotConnection]


class ChatBot:
    def __init__(self, config: BotConfig, assistant: Assistant, connect: ConnectionFactory):
        self.config = config
        self.name = config.name
        self.assistant = assistant
        self.stats = BotStats()
        self.requests = RequestTracker()
        self.connected = threading.Event()
        self.stop_event = threading.Event()
        self._connect = connect
        self._pool = ThreadPoolExecutor(max_workers=config.workers, thread_name_prefix="llm-worker")
        self._conn_lock = threading.Lock()
        self._conn: BotConnection | None = None
        self._handlers = {
            P.BOT_REQUEST: self._on_request,
            P.BOT_CANCEL: self._on_cancel,
            P.USER_LEFT: self._on_user_left,
            P.ERROR: self._on_error,
        }

    # ---- envio ------------------------------------------------------------------------
    def send(self, frame: dict) -> bool:
        with self._conn_lock:
            conn = self._conn
        return conn.send(frame) if conn else False

    def _frame(self, type_: str, to: str, req_id: str, **fields) -> dict:
        return P.make(type_, sender=self.name, to=to, req_id=req_id, **fields)

    # ---- ciclo de vida -------------------------------------------------------------
    def run(self) -> None:
        """Mantém a sessão ativa até shutdown(), reconectando quando necessário."""
        threading.Thread(target=self._heartbeat_loop, name="heartbeat", daemon=True).start()
        self._report_llm_status()
        delay = self.config.reconnect_initial
        while not self.stop_event.is_set():
            try:
                self._session()
                delay = self.config.reconnect_initial
            except (OSError, P.ProtocolError, HandshakeRejected) as exc:
                if not self.stop_event.is_set():  # no shutdown() o socket é fechado de propósito
                    log.error("%s", self._describe_failure(exc))
            if self.stop_event.is_set():
                break
            log.info("tentando reconectar em %g s...", delay)
            self.stop_event.wait(delay)
            delay = min(delay * 2, self.config.reconnect_max)

    def shutdown(self) -> None:
        """Envia BYE e fecha o socket (Ctrl+C ou comando 'sair' no console)."""
        self.stop_event.set()
        with self._conn_lock:
            conn = self._conn
        if conn:
            conn.close(goodbye=P.make(P.BYE, sender=self.name, to=P.SERVER))

    @staticmethod
    def _describe_failure(exc: Exception) -> str:
        if isinstance(exc, ssl.SSLCertVerificationError):
            return f"certificado do servidor recusado: {exc.verify_message}"
        if isinstance(exc, HandshakeRejected):
            return str(exc)
        return f"conexão com o servidor falhou: {exc}"

    def _report_llm_status(self) -> None:
        problem = self.assistant.llm.check()
        if problem:
            log.warning("ATENÇÃO: %s", problem)
        else:
            log.info("LLM pronta: %s em %s", self.config.model, self.config.ollama_url)

    def _session(self) -> None:
        conn = self._connect()
        conn.open()
        with self._conn_lock:
            self._conn = conn
        try:
            conn.handshake(P.make(P.HELLO, sender=self.name, to=P.SERVER, content={
                "role": P.ROLE_BOT, "token": self.config.token, "client": self.config.client_id}))
            self.connected.set()
            log.info("Conectado a %s:%s como '%s' — aguardando solicitações", conn.host, conn.port, self.name)
            while not self.stop_event.is_set():
                frame = conn.read_frame()
                if frame is None:
                    log.warning("servidor encerrou a conexão")
                    break
                self._dispatch(frame)
        finally:
            self.connected.clear()
            with self._conn_lock:
                self._conn = None
            self.requests.cancel_all()  # sem conexão, não há para quem responder
            conn.close()

    def _heartbeat_loop(self) -> None:
        while not self.stop_event.is_set():
            self.stop_event.wait(self.config.heartbeat_interval)
            if self.connected.is_set():
                self.send(P.make(P.PING, sender=self.name, to=P.SERVER))

    # ---- despacho de quadros -----------------------------------------------------------
    def _dispatch(self, frame: dict) -> None:
        handler = self._handlers.get(frame.get("type"))
        if handler:
            handler(frame)

    def _on_request(self, frame: dict) -> None:
        cancel = self.requests.start(frame.get("req_id"))
        self.stats.incr("requests")
        # A thread leitora só enfileira: o processamento ocorre no pool.
        self._pool.submit(self._handle_request, frame, cancel)

    def _on_cancel(self, frame: dict) -> None:
        if self.requests.cancel(frame.get("req_id")):
            log.info("%s cancelada pelo servidor (%s)", frame.get("req_id"), frame.get("content"))

    def _on_user_left(self, frame: dict) -> None:
        user = (frame.get("content") or {}).get("name")
        history = self.assistant.history
        if user and history.size(user):
            history.clear(user)
            log.info("histórico de %s descartado (saiu do chat)", user)

    def _on_error(self, frame: dict) -> None:
        log.warning("erro do servidor: %s", frame.get("content"))

    # ---- processamento (threads do pool) ---------------------------------------------------
    def _handle_request(self, frame: dict, cancel: threading.Event) -> None:
        user = frame.get("from")
        req_id = frame.get("req_id")
        question = str(frame.get("content") or "").strip()
        started = time.monotonic()
        log.info("%s de %s: %s", req_id, user, question[:80].replace("\n", " "))
        chunks = ChunkBuffer(lambda text: self.send(self._frame(P.BOT_CHUNK, user, req_id, content=text)))
        try:
            answer = self.assistant.answer(
                user, question, cancel=cancel, on_delta=chunks.add,
                on_thinking=lambda: self.send(self._frame(P.BOT_TYPING, user, req_id, content=True)))
            chunks.flush()
            self._reply(user, req_id, answer.text, started, answer.history_turns)
        except Cancelled:
            log.info("%s: processamento interrompido (cancelada)", req_id)
        except LLMError as exc:
            self.stats.incr("errors")
            log.warning("%s: %s — %s", req_id, exc.code, exc)
            self.send(self._frame(P.BOT_ERROR, user, req_id, code=exc.code,
                                  content=f"Não consegui consultar a LLM: {exc}."))
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira BOT_ERROR para o usuário
            self.stats.incr("errors")
            log.exception("%s: erro inesperado", req_id)
            self.send(self._frame(P.BOT_ERROR, user, req_id, code=ErrorCode.INTERNAL,
                                  content=f"Erro interno no bot: {exc}"))
        finally:
            self.requests.finish(req_id)

    def _reply(self, user: str, req_id: str, text: str, started: float, history_turns: int) -> None:
        elapsed = round(time.monotonic() - started, 1)
        meta = {"model": self.assistant.llm.model, "elapsed_s": elapsed,
                "history_turns": history_turns, "history_limit": self.config.history_turns}
        self.send(self._frame(P.BOT_RESPONSE, user, req_id, content=text, meta=meta))
        self.stats.incr("answered")
        log.info("%s respondida em %.1f s (histórico de %s: %s/%s turnos)",
                 req_id, elapsed, user, history_turns, self.config.history_turns)
