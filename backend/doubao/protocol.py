"""Binary WebSocket protocol helpers for Volcengine ("Doubao") speech APIs.

Both the streaming ASR ("sauc/bigmodel") and bidirectional TTS
("tts/bidirection") products use the same family of custom binary framing on
top of a plain WebSocket connection instead of a self-describing format like
protobuf/JSON-only, so client and server share this hand-rolled 4-byte header
plus size-prefixed fields. Integers are always big-endian.

References (fetched 2026-08-11):
  ASR: https://docs.volcengine.com/docs/6561/1354869 ("大模型流式语音识别API")
  TTS: https://docs.volcengine.com/docs/6561/1329505 ("WebSocket 双向流式-V3")

Layout of the 4-byte header shared by both products::

    byte 0: [protocol version:4][header size (words of 4 bytes):4]
    byte 1: [message type:4][message type specific flags:4]
    byte 2: [serialization method:4][compression method:4]
    byte 3: reserved (0x00)

After the header, most message types append optional fields (event number,
connect_id, session_id) before the final ``payload size (uint32 BE) +
payload`` pair. Which optional fields are present depends on the message
type/event, so the ASR and TTS clients each build/parse their own frames
using the primitives below rather than a single fully-generic frame class.
"""

from __future__ import annotations

import gzip
import struct
from dataclasses import dataclass

PROTOCOL_VERSION = 0b0001
HEADER_SIZE_WORDS = 0b0001  # header is HEADER_SIZE_WORDS * 4 bytes = 4 bytes

# Message types (shared meaning across ASR and TTS).
MSG_TYPE_FULL_CLIENT_REQUEST = 0b0001
MSG_TYPE_AUDIO_ONLY_REQUEST = 0b0010
MSG_TYPE_FULL_SERVER_RESPONSE = 0b1001
MSG_TYPE_AUDIO_ONLY_RESPONSE = 0b1011
MSG_TYPE_ERROR = 0b1111

# Message type specific flags.
FLAGS_NO_SEQUENCE = 0b0000
FLAGS_POSITIVE_SEQUENCE = 0b0001
FLAGS_LAST_NO_SEQUENCE = 0b0010
FLAGS_LAST_NEGATIVE_SEQUENCE = 0b0011
FLAGS_WITH_EVENT = 0b0100  # used by the TTS protocol
# Set when the frame carries a sequence number between the header and the
# payload. Not every server response does, so the field has to be skipped
# conditionally rather than always — see ``asr_client._parse_message``.
FLAGS_SEQUENCE_BIT = 0b0001

SERIALIZATION_NONE = 0b0000
SERIALIZATION_JSON = 0b0001

COMPRESSION_NONE = 0b0000
COMPRESSION_GZIP = 0b0001


def build_header(message_type: int, flags: int, serialization: int, compression: int) -> bytes:
    """Build the common 4-byte header."""
    byte0 = (PROTOCOL_VERSION << 4) | HEADER_SIZE_WORDS
    byte1 = (message_type << 4) | flags
    byte2 = (serialization << 4) | compression
    byte3 = 0x00
    return bytes([byte0, byte1, byte2, byte3])


@dataclass
class ParsedHeader:
    version: int
    header_size_bytes: int
    message_type: int
    flags: int
    serialization: int
    compression: int


def parse_header(data: bytes) -> ParsedHeader:
    if len(data) < 4:
        raise ValueError(f"frame too short to contain a header: {len(data)} bytes")
    # data[3] is reserved by the protocol and intentionally unused.
    byte0, byte1, byte2 = data[0], data[1], data[2]
    return ParsedHeader(
        version=byte0 >> 4,
        header_size_bytes=(byte0 & 0x0F) * 4,
        message_type=byte1 >> 4,
        flags=byte1 & 0x0F,
        serialization=byte2 >> 4,
        compression=byte2 & 0x0F,
    )


def maybe_compress(payload: bytes, compression: int) -> bytes:
    if compression == COMPRESSION_GZIP:
        return gzip.compress(payload)
    return payload


def maybe_decompress(payload: bytes, compression: int) -> bytes:
    if compression == COMPRESSION_GZIP and payload:
        return gzip.decompress(payload)
    return payload


def pack_u32(value: int) -> bytes:
    return struct.pack(">I", value)


def unpack_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def pack_i32(value: int) -> bytes:
    return struct.pack(">i", value)


def unpack_i32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">i", data, offset)[0]


def read_sized_field(data: bytes, offset: int) -> tuple[bytes, int]:
    """Read a ``[u32 size][bytes]`` field, returning (value, new_offset)."""
    size = unpack_u32(data, offset)
    offset += 4
    value = data[offset : offset + size]
    offset += size
    return value, offset
