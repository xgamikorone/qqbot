"""Pure codec tests; never query QQ or send messages."""

import unittest

import qq_message_id as codec

_SAMPLE = "088484f5d4ffe996ebdc0110fedce5d80238ab0e48bac78ad706"


class MessageIDTests(unittest.TestCase):
    """Checks observed samples, uint64 limits, and malformed wire inputs."""

    def test_real_sample_and_canonical_roundtrip(self) -> None:
        info = codec.decode_message_id(_SAMPLE)
        self.assertEqual(
            codec.MessageIDInfo(15913006732425380356, 723086974, 1835,
                                1793237946), info)
        self.assertEqual(
            _SAMPLE,
            codec.encode_message_id(info.guild_id, info.channel_id,
                                    info.sequence, info.timestamp))

    def test_other_channel_and_neighbor(self) -> None:
        other = "088484f5d4ffe996ebdc011095e2e5d80238870548e3de8ad706"
        self.assertEqual(723087637, codec.decode_message_id(other).channel_id)
        self.assertEqual(647, codec.decode_message_id(other).sequence)
        for offset in (-1, 0, 1):
            result = codec.decode_message_id(
                codec.generate_neighbor_message_id(_SAMPLE, offset))
            self.assertEqual(1835 + offset, result.sequence)
            self.assertEqual(1793237946, result.timestamp)
        result = codec.decode_message_id(
            codec.generate_neighbor_message_id(_SAMPLE, 1, timestamp=123))
        self.assertEqual(123, result.timestamp)

    def test_uint64_and_varint_boundaries(self) -> None:
        for value in (0, 127, 128, 16383, 16384, (1 << 64) - 1):
            with self.subTest(value=value):
                message_id = codec.encode_message_id(value, value, value, value)
                self.assertEqual(
                    codec.MessageIDInfo(value, value, value, value),
                    codec.decode_message_id(message_id))
        for value in (-1, 1 << 64, True):
            with self.assertRaises(ValueError):
                codec.encode_message_id(1, 2, value, 3)

    def test_field_order_is_normalized_not_preserved(self) -> None:
        self.assertEqual(
            "0801100238034804",
            codec.encode_message_id(
                **codec.decode_message_id("4804380310020801").__dict__))

    def test_invalid_hex_wire_types_duplicates_and_truncation(self) -> None:
        invalid = (
            "",
            "x1",
            "0",
            "08 01",
            "08",
            "0880",
            "08010801",
            "090000000000000000",
            "1801",
            "080110023803",
            "08" + "ff" * 9 + "02",
            "08" + "80" * 10 + "00",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                codec.decode_message_id(value)

    def test_neighbor_overflow_and_bad_offset(self) -> None:
        message_id = codec.encode_message_id(1, 2, 0, 3)
        with self.assertRaises(ValueError):
            codec.generate_neighbor_message_id(message_id, -1)
        with self.assertRaises(ValueError):
            codec.generate_neighbor_message_id(message_id, True)
