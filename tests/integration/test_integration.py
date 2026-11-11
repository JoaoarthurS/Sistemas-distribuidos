#!/usr/bin/env python3
"""
Teste de integração do SD Chat (evidência de testes para o relatório).

Sobe o servidor e o bot como processos separados, um Ollama simulado
(respostas determinísticas) e três clientes humanos (dois com TLS e um sem),
e verifica os cenários exigidos no enunciado.

Uso:  python tests/integration/test_integration.py
"""

from __future__ import annotations

import json
import queue
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # executado como script: a raiz do projeto não está no path

import mock_ollama  # noqa: E402  (mesma pasta deste arquivo)
from common import protocol as P  # noqa: E402
from common import tls  # noqa: E402
from common.transport import SafeSocket  # noqa: E402

CA = str(ROOT / "certs" / "ca.crt")
TOKEN = "token-de-teste"
REQUEST_TIMEOUT = 6
results: list[tuple[bool, str]] = []


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check(cond: bool, desc: str) -> bool:
    results.append((bool(cond), desc))
    print(f"  {'OK  ' if cond else 'FALHA'} {desc}", flush=True)
    return bool(cond)


class TestClient:
    def __init__(self, name: str, port: int, secure: bool, role: str = "human",
                 token: str | None = None, ca: str | None = CA):
        raw = socket.create_connection(("127.0.0.1", port), timeout=5)
        if secure:
            raw = tls.client_context(ca).wrap_socket(raw, server_hostname="127.0.0.1")
        self.sock = SafeSocket(raw)  # leitora em thread própria + envios da thread principal
        self.name = name
        self.frames: queue.Queue = queue.Queue()
        self.seen: list[dict] = []
        self.closed = threading.Event()
        threading.Thread(target=self._reader, daemon=True).start()
        content = {"role": role, "client": "teste"}
        if token:
            content["token"] = token
        self.send(P.make(P.HELLO, sender=name, to=P.SERVER, content=content))

    def _reader(self):
        reader = P.FrameReader(self.sock)
        try:
            while True:
                f = reader.read_frame()
                if f is None:
                    break
                self.frames.put(f)
        except OSError:
            pass
        self.closed.set()

    def send(self, frame: dict) -> dict:
        self.sock.sendall(P.encode(frame))
        return frame

    def msg(self, to: str, text: str) -> dict:
        return self.send(P.make(P.MSG, sender=self.name, to=to, content=text))

    def expect(self, pred, timeout: float = 5.0) -> dict | None:
        """Espera um quadro que satisfaça pred (procura também nos já recebidos)."""
        for f in self.seen:
            if pred(f):
                self.seen.remove(f)
                return f
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                f = self.frames.get(timeout=max(0.01, end - time.monotonic()))
            except queue.Empty:
                break
            if pred(f):
                return f
            self.seen.append(f)
        return None

    def drain(self, wait: float = 0.3) -> list[dict]:
        time.sleep(wait)
        while True:
            try:
                self.seen.append(self.frames.get_nowait())
            except queue.Empty:
                break
        out, self.seen = self.seen, []
        return out

    def close(self, graceful: bool = True):
        try:
            if graceful:
                self.send(P.make(P.BYE, sender=self.name, to=P.SERVER))
            self.sock.close()
        except OSError:
            pass


def typ(t, **kw):
    return lambda f: f.get("type") == t and all(f.get(k) == v for k, v in kw.items())


def main() -> int:
    tls_port, plain_port, dash_port = free_port(), free_port(), free_port()
    mock = mock_ollama.start()
    mock_url = f"http://127.0.0.1:{mock.server_address[1]}"
    py = sys.executable
    procs = []
    try:
        server = subprocess.Popen([py, "-m", "server", "--no-browser",
                                   "--tls-port", str(tls_port), "--plain-port", str(plain_port),
                                   "--dashboard-port", str(dash_port), "--bot-token", TOKEN,
                                   "--request-timeout", str(REQUEST_TIMEOUT)],
                                  cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(server)
        time.sleep(1.2)
        bot = subprocess.Popen([py, "-m", "bot", "--port", str(tls_port),
                                "--token", TOKEN, "--ollama", mock_url, "--model", "mock",
                                "--llm-timeout", "3", "--history", "4"],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(bot)
        time.sleep(1.5)

        print("\n[1] Conexões, identificação e TLS")
        ana = TestClient("Ana", tls_port, secure=True)
        w = ana.expect(typ(P.WELCOME))
        check(w and w["content"]["secure"] and w["content"]["tls"]["version"].startswith("TLS"),
              f"Ana conectou via TLS ({w and w['content']['tls']})")
        check(w and any(u["name"] == "bot" and u["role"] == "bot" for u in w["content"]["users"]),
              "lista de usuários do WELCOME inclui o bot")
        bruno = TestClient("Bruno", tls_port, secure=True)
        check(bruno.expect(typ(P.WELCOME)) is not None, "Bruno conectou via TLS")
        carla = TestClient("Carla", plain_port, secure=False)
        wc = carla.expect(typ(P.WELCOME))
        check(wc and wc["content"]["secure"] is False, "Carla conectou via TCP sem criptografia (referência)")
        j = ana.expect(lambda f: f["type"] == P.USER_JOINED and f["content"]["name"] == "Carla")
        check(j is not None, "Ana recebeu USER_JOINED de Carla")

        dup = TestClient("ana", tls_port, secure=True)
        e = dup.expect(typ(P.ERROR))
        check(e and e.get("code") == "NAME_TAKEN", "nome duplicado ('ana') recusado com NAME_TAKEN")
        check(dup.closed.wait(3), "conexão com nome duplicado foi encerrada pelo servidor")

        try:
            TestClient("Mallory", tls_port, secure=True, ca=None)  # confia só nas CAs do sistema
            check(False, "cliente sem a CA do projeto deveria rejeitar o certificado")
        except ssl.SSLCertVerificationError as exc:
            check(True, f"cliente que não confia na CA rejeita o servidor ({exc.verify_message})")

        print("\n[2] Mensagens públicas, privadas e delimitação")
        m = ana.msg("*", "Olá, pessoal! Mensagem com acentuação: ção, é, ü 🚀")
        ack = ana.expect(typ(P.ACK, ref=m["id"]))
        check(ack and ack["content"]["recipients"] == 2, "ACK do broadcast indica 2 destinatários")
        for c in (bruno, carla):
            f = c.expect(typ(P.MSG, ref=None))
            check(f and f["from"] == "Ana" and f["content"] == m["content"] and f["to"] == "*",
                  f"{c.name} recebeu a mensagem pública de Ana com o texto intacto")
        check(ana.expect(typ(P.MSG), timeout=0.5) is None, "Ana não recebe eco da própria mensagem")

        m = bruno.msg("Carla", "Oi Carla, isto é privado")
        f = carla.expect(typ(P.MSG))
        check(f and f["from"] == "Bruno" and f["to"] == "Carla", "mensagem privada Bruno → Carla entregue")
        check(ana.expect(typ(P.MSG), timeout=0.5) is None, "Ana não recebe a mensagem privada")

        spoof = P.make(P.MSG, sender="Bruno", to="Carla", content="sou o Bruno?")
        ana.send(spoof)
        f = carla.expect(typ(P.MSG))
        check(f and f["from"] == "Ana", "servidor ignora 'from' falsificado (remetente vem da conexão)")

        burst = [P.make(P.MSG, sender="Bruno", to="Ana", content=f"rajada {i}") for i in range(20)]
        bruno.sock.sendall(b"".join(P.encode(x) for x in burst))  # vários quadros num único send
        got = [ana.expect(typ(P.MSG, **{"from": "Bruno"}), 3) for _ in range(20)]
        check(all(got) and [g["content"] for g in got] == [f"rajada {i}" for i in range(20)],
              "20 quadros enviados num único segmento chegam separados e em ordem")

        bruno.sock.sendall(b'{isto nao e json}\n')
        e = bruno.expect(typ(P.ERROR))
        check(e and e.get("code") == "BAD_FRAME", "JSON inválido gera ERROR BAD_FRAME sem derrubar a conexão")
        m = bruno.msg("*", "ainda conectado")
        check(bruno.expect(typ(P.ACK, ref=m["id"])) is not None, "Bruno continua enviando após o erro")
        carla.drain(); ana.drain()

        print("\n[3] Bot: correlação, privacidade e concorrência")
        q = ana.msg("*", "@bot Qual a diferença entre TCP e UDP?")
        ack = ana.expect(typ(P.ACK, ref=q["id"]))
        rid = ack and ack.get("req_id")
        check(rid and ack["content"]["status"] == "queued", f"servidor criou a solicitação {rid}")
        typing_ = ana.expect(typ(P.BOT_TYPING, req_id=rid))
        check(typing_ is not None, "Ana recebeu BOT_TYPING com o mesmo req_id")
        # enquanto o bot gera a resposta, os outros continuam conversando
        t0 = time.monotonic()
        m = bruno.msg("Carla", "conversa paralela durante a consulta ao bot")
        f = carla.expect(typ(P.MSG))
        lat = time.monotonic() - t0
        check(f is not None and lat < 0.5, f"Bruno → Carla entregue em {lat * 1000:.0f} ms durante a consulta")
        early = [x for x in list(ana.frames.queue) + ana.seen if x["type"] == P.BOT_RESPONSE]
        check(f is not None and not early, "mensagem paralela chegou ANTES da resposta do bot terminar")
        resp = ana.expect(typ(P.BOT_RESPONSE, req_id=rid), timeout=10)
        chunks = [x for x in ana.drain(0) if x["type"] == P.BOT_CHUNK]
        check(resp is not None and "turnos anteriores: 0" in resp["content"],
              "resposta final chegou à Ana, correlacionada pelo req_id")
        check(len(chunks) >= 2 and all(c["req_id"] == rid for c in chunks),
              f"resposta transmitida em {len(chunks)} pedaços (BOT_CHUNK) com o mesmo req_id")
        check(resp and resp["ref"] == q["id"] and resp["meta"]["history_limit"] == 4,
              "BOT_RESPONSE referencia a mensagem original e informa o limite de histórico")
        for c in (bruno, carla):
            leaked = [x for x in c.drain() if x["type"].startswith("BOT_") or "TCP e UDP" in str(x.get("content"))]
            check(not leaked, f"{c.name} não recebeu nada da conversa privada Ana ↔ bot")

        print("\n[4] Histórico por usuário e pergunta de continuação")
        q2 = ana.send(P.make(P.MSG, sender="Ana", to="bot", content="E qual dos dois é mais rápido?"))
        rid2 = ana.expect(typ(P.ACK, ref=q2["id"]))["req_id"]
        r2 = ana.expect(typ(P.BOT_RESPONSE, req_id=rid2), timeout=10)
        check(r2 and "turnos anteriores: 1" in r2["content"] and "TCP e UDP" in r2["content"],
              "continuação da Ana recebeu a pergunta anterior no contexto")
        q3 = bruno.msg("*", "@bot E qual é mais rápido?")
        rid3 = bruno.expect(typ(P.ACK, ref=q3["id"]))["req_id"]
        r3 = bruno.expect(typ(P.BOT_RESPONSE, req_id=rid3), timeout=10)
        check(r3 and "turnos anteriores: 0" in r3["content"], "contexto do Bruno é separado do da Ana")
        qa, qb = ana.msg("bot", "pergunta simultânea A"), bruno.msg("bot", "pergunta simultânea B")
        ra = ana.expect(typ(P.ACK, ref=qa["id"]))["req_id"]
        rb = bruno.expect(typ(P.ACK, ref=qb["id"]))["req_id"]
        fa = ana.expect(typ(P.BOT_RESPONSE, req_id=ra), timeout=10)
        fb = bruno.expect(typ(P.BOT_RESPONSE, req_id=rb), timeout=10)
        check(fa and fb and "simultânea A" in fa["content"] and "simultânea B" in fb["content"],
              "duas perguntas simultâneas: cada resposta foi para o usuário certo")
        for i in range(4):
            qx = ana.msg("bot", f"enchendo histórico {i}")
            rx = ana.expect(typ(P.ACK, ref=qx["id"]))["req_id"]
            last = ana.expect(typ(P.BOT_RESPONSE, req_id=rx), timeout=10)
        check(last and last["meta"]["history_turns"] == 4 and "turnos anteriores: 4" in last["content"],
              "histórico limitado a 4 turnos por usuário")
        qr = ana.msg("bot", "/reset")
        rr = ana.expect(typ(P.BOT_RESPONSE, req_id=ana.expect(typ(P.ACK, ref=qr["id"]))["req_id"]))
        check(rr and rr["meta"]["history_turns"] == 0, "comando /reset apaga o histórico")

        print("\n[5] Falhas: tempo limite da LLM, desconexões e bot offline")
        ql = ana.msg("*", "@bot [lento] demore bastante")
        ridl = ana.expect(typ(P.ACK, ref=ql["id"]))["req_id"]
        el = ana.expect(typ(P.BOT_ERROR, req_id=ridl), timeout=10)
        check(el and el.get("code") == "LLM_TIMEOUT", f"consulta lenta gerou BOT_ERROR LLM_TIMEOUT: {el and el['content']}")

        carla.close(graceful=False)  # queda abrupta, sem BYE
        for c in (ana, bruno):
            f = c.expect(lambda x: x["type"] == P.USER_LEFT and x["content"]["name"] == "Carla")
            check(f is not None, f"{c.name} recebeu USER_LEFT de Carla ({f and f['content']['reason']})")
        m = ana.msg("Carla", "ainda está aí?")
        e = ana.expect(typ(P.ERROR, ref=m["id"]))
        check(e and e.get("code") == "USER_NOT_FOUND", "mensagem para usuário desconectado gera USER_NOT_FOUND")

        bot.terminate()
        bot.wait(5)
        f = ana.expect(lambda x: x["type"] == P.USER_LEFT and x["content"]["name"] == "bot", timeout=5)
        check(f is not None, "queda do processo do bot detectada (USER_LEFT bot)")
        m = ana.msg("*", "@bot alguém aí?")
        e = ana.expect(typ(P.BOT_ERROR, ref=m["id"]))
        check(e and e.get("code") == "BOT_OFFLINE", "pergunta sem bot conectado gera BOT_OFFLINE")

        print("\n[6] Servidor: autenticação do bot, validação de correlação e tempo limite")
        intruso = TestClient("bot", tls_port, secure=True, role="bot", token="errado")
        e = intruso.expect(typ(P.ERROR))
        check(e and e.get("code") == "BAD_TOKEN", "bot com token errado é recusado")
        fake = TestClient("bot", tls_port, secure=True, role="bot", token=TOKEN)
        check(fake.expect(typ(P.WELCOME)) is not None, "bot de teste (que não responde) conectado")
        m = ana.msg("*", "@bot responda se puder")
        rid = ana.expect(typ(P.ACK, ref=m["id"]))["req_id"]
        req = fake.expect(typ(P.BOT_REQUEST, req_id=rid))
        check(req and req["from"] == "Ana" and req["content"] == "responda se puder",
              "bot recebeu BOT_REQUEST com remetente, req_id e pergunta sem a menção")
        fake.send(P.make(P.BOT_CHUNK, sender="bot", to="Bruno", req_id=rid, content="desviado?"))
        f = ana.expect(typ(P.BOT_CHUNK, req_id=rid))
        check(f and f["to"] == "Ana", "destinatário errado indicado pelo bot é corrigido para o solicitante")
        check(not [x for x in bruno.drain() if x.get("req_id") == rid], "Bruno não recebeu o pedaço desviado")
        fake.send(P.make(P.BOT_RESPONSE, sender="bot", to="Ana", req_id="R9999", content="inventada"))
        check(ana.expect(typ(P.BOT_RESPONSE), timeout=1) is None, "resposta com req_id desconhecido é descartada")
        e = ana.expect(typ(P.BOT_ERROR, req_id=rid), timeout=REQUEST_TIMEOUT + 3)
        check(e and e.get("code") == "TIMEOUT", f"servidor expirou a solicitação após {REQUEST_TIMEOUT} s")
        c = fake.expect(typ(P.BOT_CANCEL, req_id=rid))
        check(c is not None, "bot recebeu BOT_CANCEL da solicitação expirada")

        print("\n[7] Painel do servidor")
        with urllib.request.urlopen(f"http://127.0.0.1:{dash_port}/api/state", timeout=5) as r:
            st = json.load(r)
        names = {c["name"]: c for c in st["clients"]}
        check({"Ana", "Bruno", "bot"} <= set(names), f"painel lista participantes: {sorted(n for n in names if n)}")
        check(names["Ana"]["secure"] and names["Ana"]["tls"]["version"].startswith("TLS"), "painel indica o enlace TLS da Ana")
        tnames = [t["name"] for t in st["threads"]]
        check({"leitor-Ana", "escritor-Ana", "watchdog-bot"} <= set(tnames),
              f"painel mostra as threads ({len(tnames)} ativas)")
        check(st["stats"]["bot_timeouts"] >= 1 and st["stats"]["messages_private"] >= 1, "estatísticas atualizadas")
        check(any(m["kind"] == "bot_response" for m in st["messages"]), "painel registra mensagens do bot")
        ana.close(); bruno.close(); fake.close()
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        mock.shutdown()

    ok = sum(1 for r, _ in results if r)
    print(f"\nResultado: {ok}/{len(results)} verificações passaram.")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    sys.exit(main())
