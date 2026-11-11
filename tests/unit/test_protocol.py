"""Testes do protocolo: codificação, decodificação e delimitação de quadros."""

import unittest

from common import protocol as P


class FakeSocket:
    """Entrega os bytes em pedaços arbitrários, como o TCP faz."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def recv(self, _size):
        return self._chunks.pop(0) if self._chunks else b""


class EncodeDecodeTest(unittest.TestCase):
    def test_round_trip_preserves_unicode(self):
        frame = P.make(P.MSG, sender="Ana", to=P.BROADCAST, content="ção 🚀\nsegunda linha")
        data = P.encode(frame)
        self.assertTrue(data.endswith(P.DELIMITER))
        self.assertEqual(data.count(P.DELIMITER), 1, "quebras de linha do texto ficam escapadas no JSON")
        self.assertEqual(P.decode(data[:-1]), frame)

    def test_make_omits_empty_optional_fields(self):
        frame = P.make(P.ERROR, code=None, ref="abc")
        self.assertNotIn("code", frame)
        self.assertNotIn("req_id", frame)
        self.assertEqual(frame["ref"], "abc")

    def test_decode_rejects_invalid_json_and_missing_type(self):
        with self.assertRaises(P.ProtocolError):
            P.decode(b"{nao e json}")
        with self.assertRaises(P.ProtocolError):
            P.decode(b'{"content": "sem tipo"}')

    def test_encode_rejects_oversized_frame(self):
        with self.assertRaises(P.FrameTooLarge):
            P.encode(P.make(P.MSG, content="x" * P.MAX_FRAME_BYTES))


class FrameReaderTest(unittest.TestCase):
    def test_split_and_coalesced_frames(self):
        a = P.encode(P.make(P.MSG, content="primeiro"))
        b = P.encode(P.make(P.MSG, content="segundo"))
        stream = a + b
        # meio quadro, depois o resto do primeiro junto com o segundo inteiro
        reader = P.FrameReader(FakeSocket([stream[:7], stream[7:]]))
        self.assertEqual(reader.read_frame()["content"], "primeiro")
        self.assertEqual(reader.read_frame()["content"], "segundo")
        self.assertIsNone(reader.read_frame())
        self.assertEqual(reader.bytes_read, len(stream))

    def test_invalid_frame_does_not_break_the_stream(self):
        ok = P.encode(P.make(P.PING))
        reader = P.FrameReader(FakeSocket([b"{quebrado}\n" + ok]))
        with self.assertRaises(P.ProtocolError):
            reader.read_frame()
        self.assertEqual(reader.read_frame()["type"], P.PING)

    def test_frame_without_delimiter_is_limited(self):
        reader = P.FrameReader(FakeSocket([b"x" * 200]), max_bytes=100)
        with self.assertRaises(P.FrameTooLarge):
            reader.read_frame()


if __name__ == "__main__":
    unittest.main()
