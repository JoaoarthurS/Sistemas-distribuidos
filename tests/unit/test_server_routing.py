"""Testes do roteamento e da intermediação com o bot — sem sockets.

Como MessageRouter, SessionManager e BotBroker dependem apenas da interface
de uma conexão (send, name, role...), basta uma conexão falsa que guarda os
quadros enviados.
"""

import logging
import time
import unittest

from common import protocol as P
from common.protocol import ErrorCode
from server.bot_broker import BotBroker
from server.config import ServerConfig
from server.monitor import Monitor
from server.registry import ClientRegistry
from server.router import MessageRouter
from server.sessions import SessionManager
from server.validation import RejectConnection

logging.getLogger("server").setLevel(logging.WARNING)


class FakeConnection:
    _next = 1

    def __init__(self, secure=True):
        self.cid = FakeConnection._next
        FakeConnection._next += 1
        self.secure = secure
        self.tls = {"version": "TLSv1.3"} if secure else None
        self.name = self.role = None
        self.client_info = ""
        self.address = f"127.0.0.1:{50000 + self.cid}"
        self.sent: list[dict] = []

    label = property(lambda self: self.name or f"#{self.cid}")
    is_human = property(lambda self: self.role == P.ROLE_HUMAN)
    is_bot = property(lambda self: self.role == P.ROLE_BOT)

    def identify(self, identity):
        self.name, self.role, self.client_info = identity.name, identity.role, identity.client

    def public_info(self):
        return {"name": self.name, "role": self.role, "secure": self.secure, "client": self.client_info}

    def send(self, frame):
        self.sent.append(frame)
        return True

    def take(self, type_=None):
        out = [f for f in self.sent if type_ is None or f["type"] == type_]
        self.sent = [f for f in self.sent if f not in out]
        return out


class RoutingTest(unittest.TestCase):
    def setUp(self):
        self.config = ServerConfig(bot_token="tk", request_timeout=0.05)
        self.monitor = Monitor()
        self.registry = ClientRegistry()
        self.broker = BotBroker(self.registry, self.monitor, request_timeout=self.config.request_timeout,
                                max_pending_per_user=self.config.max_pending_per_user)
        self.sessions = SessionManager(self.registry, self.broker, self.monitor, self.config)
        self.router = MessageRouter(self.registry, self.broker, self.monitor, bot_name="bot")

    def join(self, name, role="human", **content):
        conn = FakeConnection()
        self.registry.track(conn)
        self.sessions.join(conn, P.make(P.HELLO, sender=name, content={"role": role, **content}))
        conn.take()  # descarta WELCOME/USER_JOINED
        return conn

    def msg(self, conn, to, text):
        frame = P.make(P.MSG, sender=conn.name, to=to, content=text)
        self.router.route(conn, frame)
        return frame

    # ---- sessões ---------------------------------------------------------------------
    def test_duplicate_name_is_rejected_case_insensitively(self):
        self.join("Ana")
        dup = FakeConnection()
        with self.assertRaises(RejectConnection):
            self.sessions.join(dup, P.make(P.HELLO, sender="ANA", content={"role": "human"}))
        self.assertEqual(dup.take(P.ERROR)[0]["code"], ErrorCode.NAME_TAKEN)

    # ---- mensagens ---------------------------------------------------------------------
    def test_public_message_reaches_other_humans_only(self):
        ana, bruno, bot = self.join("Ana"), self.join("Bruno"), self.join("bot", "bot", token="tk")
        m = self.msg(ana, P.BROADCAST, "oi")
        received = bruno.take(P.MSG)[0]
        self.assertEqual((received["content"], received["id"]), ("oi", m["id"]))
        self.assertEqual(ana.take(P.ACK)[0]["content"]["recipients"], 1)
        self.assertEqual(ana.take(P.MSG), [], "sem eco para o remetente")
        self.assertEqual(bot.take(P.MSG), [], "bot não recebe a Sala Geral")

    def test_private_message_to_offline_user(self):
        ana = self.join("Ana")
        m = self.msg(ana, "Carla", "oi")
        err = ana.take(P.ERROR)[0]
        self.assertEqual((err["code"], err["ref"]), (ErrorCode.USER_NOT_FOUND, m["id"]))

    def test_role_not_allowed_for_frame_type(self):
        bot = self.join("bot", "bot", token="tk")
        self.router.route(bot, P.make(P.MSG, to=P.BROADCAST, content="humano?"))
        self.assertEqual(bot.take(P.ERROR)[0]["code"], ErrorCode.BAD_TYPE)

    # ---- bot ----------------------------------------------------------------------------
    def test_mention_creates_request_and_reply_goes_only_to_requester(self):
        ana, bruno, bot = self.join("Ana"), self.join("Bruno"), self.join("bot", "bot", token="tk")
        m = self.msg(ana, P.BROADCAST, "@bot o que é TLS?")
        ack = ana.take(P.ACK)[0]
        req = bot.take(P.BOT_REQUEST)[0]
        self.assertEqual((req["content"], req["from"], req["req_id"]), ("o que é TLS?", "Ana", ack["req_id"]))

        # o bot indica o destinatário errado: o servidor corrige para o solicitante
        self.router.route(bot, P.make(P.BOT_RESPONSE, sender="bot", to="Bruno", req_id=req["req_id"],
                                      content="resposta"))
        resp = ana.take(P.BOT_RESPONSE)[0]
        self.assertEqual((resp["to"], resp["ref"]), ("Ana", m["id"]))
        self.assertEqual([f for f in bruno.sent if f["type"].startswith("BOT_")], [], "Bruno não vê a resposta")
        self.assertEqual(self.broker.snapshot(), [], "resposta final encerra a solicitação")

    def test_bot_offline(self):
        ana = self.join("Ana")
        self.msg(ana, P.BROADCAST, "@bot alguém?")
        self.assertEqual(ana.take(P.BOT_ERROR)[0]["code"], ErrorCode.BOT_OFFLINE)

    def test_pending_limit_per_user(self):
        ana, _bot = self.join("Ana"), self.join("bot", "bot", token="tk")
        for i in range(self.config.max_pending_per_user + 1):
            self.msg(ana, "bot", f"pergunta {i}")
        self.assertEqual(len(ana.take(P.ACK)), self.config.max_pending_per_user)
        self.assertEqual(ana.take(P.ERROR)[0]["code"], ErrorCode.TOO_MANY_REQUESTS)

    def test_timeout_and_bot_disconnect(self):
        ana, bot = self.join("Ana"), self.join("bot", "bot", token="tk")
        self.msg(ana, "bot", "pergunta lenta")
        rid = bot.take(P.BOT_REQUEST)[0]["req_id"]
        time.sleep(self.config.request_timeout * 2)
        self.assertEqual(self.broker.expire_overdue(), 1)
        self.assertEqual(ana.take(P.BOT_ERROR)[0]["code"], ErrorCode.TIMEOUT)
        self.assertEqual(bot.take(P.BOT_CANCEL)[0]["req_id"], rid)

        self.msg(ana, "bot", "outra")
        self.sessions.leave(bot, "caiu", registered=True)
        self.assertEqual(ana.take(P.USER_LEFT)[0]["content"]["name"], "bot")
        self.assertEqual(ana.take(P.BOT_ERROR)[0]["code"], ErrorCode.BOT_OFFLINE)


if __name__ == "__main__":
    unittest.main()
