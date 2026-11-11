"""Testes das regras de validação do servidor (funções puras)."""

import unittest

from common import protocol as P
from common.protocol import ErrorCode
from server.validation import RejectConnection, parse_mention, validate_hello


def hello(name, **content):
    return P.make(P.HELLO, sender=name, to=P.SERVER, content=content or {"role": "human"})


class ValidateHelloTest(unittest.TestCase):
    def test_accepts_human_and_truncates_client_info(self):
        identity = validate_hello(hello("João.S", role="human", client="x" * 100), "tk")
        self.assertEqual((identity.name, identity.role), ("João.S", P.ROLE_HUMAN))
        self.assertEqual(len(identity.client), 60)
        self.assertEqual(identity.key, "joão.s")

    def test_rejections_carry_protocol_codes(self):
        cases = [
            (P.make(P.MSG, sender="Ana"), ErrorCode.HELLO_REQUIRED),
            (hello("Ana", role="admin"), ErrorCode.BAD_ROLE),
            (hello("A"), ErrorCode.BAD_NAME),
            (hello("com espaço"), ErrorCode.BAD_NAME),
            (hello("servidor"), ErrorCode.BAD_NAME),
            (hello("bot", role="bot", token="errado"), ErrorCode.BAD_TOKEN),
        ]
        for frame, code in cases:
            with self.subTest(code=code, frame=frame.get("from")):
                with self.assertRaises(RejectConnection) as ctx:
                    validate_hello(frame, "tk")
                self.assertEqual(ctx.exception.code, code)

    def test_bot_with_valid_token(self):
        self.assertEqual(validate_hello(hello("bot", role="bot", token="tk"), "tk").role, P.ROLE_BOT)


class MentionTest(unittest.TestCase):
    def test_parse_mention(self):
        m = parse_mention("  @Bot, qual a diferença\nentre TCP e UDP?")
        self.assertEqual(m.name, "Bot")
        self.assertEqual(m.text, "qual a diferença\nentre TCP e UDP?")
        self.assertTrue(m.targets("bot"))

    def test_text_without_mention(self):
        self.assertIsNone(parse_mention("olá @bot"))


if __name__ == "__main__":
    unittest.main()
