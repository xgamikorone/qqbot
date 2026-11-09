"""Experimental codec for the observed QQ channel ID wire format.

This is not a published QQ protocol or an authorization mechanism. Always use
the original ID returned by QQ for replies, not a synthesized candidate.
"""

import dataclasses
import re

_UINT64_MAX = (1 << 64) - 1
_FIELDS = (1, 2, 7, 9)


@dataclasses.dataclass(frozen=True)
class MessageIDInfo:
    """Observed numeric fields, without claiming server-side semantics."""

    guild_id: int
    channel_id: int
    sequence: int
    timestamp: int


def _uint64(value: int) -> int:
    if type(value) is not int or not 0 <= value <= _UINT64_MAX:
        raise ValueError("Expected a uint64 integer")
    return value


def _encode_varint(value: int) -> bytes:
    value = _uint64(value)
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for index in range(10):
        if offset >= len(data):
            raise ValueError("Truncated varint")
        byte = data[offset]
        offset += 1
        if index == 9 and byte > 1:
            raise ValueError("Varint exceeds uint64")
        value |= (byte & 127) << (7 * index)
        if byte < 128:
            return value, offset
    raise ValueError("Unterminated varint")


def decode_message_id(message_id: str) -> MessageIDInfo:
    """Decodes exactly the four observed varint fields.

    Args:
        message_id: Original or constructed hexadecimal ID.

    Returns:
        The observed fields, independent of their original ordering.

    Raises:
        ValueError: Hex, fields, duplicates, or integer ranges are invalid.
    """
    if (not isinstance(message_id, str) or len(message_id) > 100 or
            len(message_id) % 2 or
            not re.fullmatch(r"[0-9a-fA-F]+", message_id)):
        raise ValueError("Invalid hexadecimal message ID")
    data = bytes.fromhex(message_id)
    offset = 0
    fields: dict[int, int] = {}
    while offset < len(data):
        tag, offset = _decode_varint(data, offset)
        number = tag >> 3
        if tag & 7 or number not in _FIELDS or number in fields:
            raise ValueError("Unsupported or duplicate message ID field")
        fields[number], offset = _decode_varint(data, offset)
    if set(fields) != set(_FIELDS):
        raise ValueError("Missing message ID fields")
    return MessageIDInfo(*(fields[number] for number in _FIELDS))


def encode_message_id(guild_id: int, channel_id: int, sequence: int,
                      timestamp: int) -> str:
    """Encodes the observed fields in canonical order, for lookup only."""
    values = (guild_id, channel_id, sequence, timestamp)
    return b"".join(
        _encode_varint(number << 3) + _encode_varint(value)
        for number, value in zip(_FIELDS, values)).hex()


def decode_lookup_identity(value: str) -> tuple[str, int, int, int]:
    """Recognizes compact/expanded lookup IDs observed in user API samples.

    This is experimental lookup equivalence, not authorization. Field 1 has
    different values across these formats and is not treated as a guild ID.
    Unknown layouts, duplicate fields and unsupported wire types fail closed.
    """
    if (
        not isinstance(value, str)
        or len(value) > 512
        or len(value) % 2
        or not re.fullmatch(r"[0-9a-fA-F]+", value)
    ):
        raise ValueError("Invalid lookup ID")
    data = bytes.fromhex(value)
    fields: dict[int, int | bytes] = {}
    offset = 0
    while offset < len(data):
        tag, offset = _decode_varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if number in fields:
            raise ValueError("Duplicate lookup ID field")
        if wire == 0:
            item, offset = _decode_varint(data, offset)
            fields[number] = item
        elif wire == 2 and number == 3:
            size, offset = _decode_varint(data, offset)
            if offset + size > len(data):
                raise ValueError("Truncated lookup ID field")
            fields[number] = data[offset : offset + size]
            offset += size
        else:
            raise ValueError("Unsupported lookup ID wire type")
    if set(fields) == {1, 2, 7, 9}:
        layout = "compact"
    elif (
        set(fields) == {1, 2, 3, 4, 5, 6, 7, 8, 9, 11}
        and isinstance(fields[3], bytes)
        and fields[7] == fields[8]
    ):
        layout = "expanded"
    else:
        raise ValueError("Unsupported lookup ID layout")
    channel, sequence, timestamp = fields[2], fields[7], fields[9]
    if not all(
        isinstance(item, int) for item in (channel, sequence, timestamp)
    ):
        raise ValueError("Invalid lookup identity fields")
    assert (
        isinstance(channel, int)
        and isinstance(sequence, int)
        and isinstance(timestamp, int)
    )
    return layout, channel, sequence, timestamp


def generate_neighbor_message_id(
    message_id: str, sequence_offset: int, timestamp: int | None = None
) -> str:
    """Builds a uint64 sequence candidate, preserving time by default."""
    if type(sequence_offset) is not int:
        raise ValueError("Sequence offset must be an integer")
    info = decode_message_id(message_id)
    return encode_message_id(
        info.guild_id,
        info.channel_id,
        info.sequence + sequence_offset,
        info.timestamp if timestamp is None else timestamp,
    )
