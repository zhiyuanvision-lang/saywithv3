"""Raw asyncio client for Volcengine's streaming ASR ("大模型流式语音识别API").

This is a thin, Pipecat-independent client so it can be exercised directly by
``scripts/smoketest_doubao.py`` against the real service. The Pipecat
adapter (``app/pipecat_services/asr_service.py``) wraps this class.

Doc: https://docs.volcengine.com/docs/6561/1354869 (fetched 2026-08-11)

Design notes:
  - We use the "双向流式模式（优化版本）" endpoint (``/api/v3/sauc/bigmodel_async``)
    with two-pass recognition (``enable_nonstream``) on: responses stream
    back while the learner is still talking, and when the sentence ends the
    service re-recognises that audio with its non-streaming model and sends
    the better transcript as the final response.

    The plain ``/api/v3/sauc/bigmodel`` endpoint we used until 反馈 366 has
    only the streaming pass, and on a Chinese learner's English it leans on
    its Chinese prior hard enough to answer in the wrong language: measured
    on the same clips, "He's a born liar." came back as "Use a bomb.",
    "He is a constant liar." as "和 is a constant liar。", the single word
    "liar" as "Li." and "constant" as "Const.". Two-pass got all four
    right. The learner's *grammar* mistakes still survive both passes
    ("we forget the water" stayed wrong), which is what the lesson needs —
    see ``scripts/asr_faithfulness.py``.
  - ``result.text`` from each server response is the *cumulative* transcript
    for everything sent on this WebSocket connection so far, not just the
    latest utterance (confirmed against the docs' own multi-sentence
    example). Callers that want "this turn's text" should open a fresh
    connection per user turn — see ``DoubaoASRService`` in the Pipecat
    adapter, which does exactly that.
  - Auth uses the new-console single ``X-Api-Key`` header — this must be a
    "火山引擎 - 语音技术" console key, NOT an Ark LLM ``ark-...`` key (the
    latter authenticates fine at the TCP/HTTP-upgrade level but the service
    then rejects it, so this is easy to misdiagnose as a protocol bug).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

import websockets
from websockets.asyncio.client import ClientConnection

from . import protocol as proto

logger = logging.getLogger(__name__)

ASR_WS_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"

# Inline hotwords go in the initial request and are budgeted in tokens by the
# service (~100 in bidirectional streaming mode), so the list has to stay
# short. Today's words are exactly the words the learner is least fluent in
# and therefore most likely to have mis-recognised, which is the case
# keyword biasing is for.
MAX_HOTWORDS = 40


@dataclass
class AsrResult:
    """One parsed "full server response" from the ASR service."""

    text: str
    is_last: bool
    raw: dict
    log_id: str | None = None


@dataclass
class AsrErrorResult:
    code: int
    message: str


class DoubaoASRError(RuntimeError):
    pass


def _clean_hotwords(words: Sequence[str] | None) -> list[str]:
    """Dedupes, trims and caps a hotword list, preserving order."""
    if not words:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in words:
        word = (raw or "").strip()
        if not word or word.lower() in seen:
            continue
        seen.add(word.lower())
        out.append(word)
        if len(out) >= MAX_HOTWORDS:
            break
    return out


class DoubaoASRClient:
    """One streaming-ASR "utterance" over one WebSocket connection.

    Usage::

        client = DoubaoASRClient(api_key=..., resource_id=...)
        await client.connect()
        await client.send_audio(chunk1)
        await client.send_audio(chunk2)
        await client.send_audio(b"", is_last=True)
        async for result in client.responses():
            ...
        await client.close()
    """

    def __init__(
        self,
        *,
        api_key: str,
        resource_id: str = "volc.seedasr.sauc.duration",
        sample_rate: int = 16000,
        language: str | None = None,
        enable_punc: bool = True,
        enable_itn: bool = True,
        two_pass: bool = True,
        uid: str = "saywith-voice-gateway",
        hotwords: Sequence[str] | None = None,
    ):
        self._api_key = api_key
        self._resource_id = resource_id
        self._sample_rate = sample_rate
        self._language = language
        self._two_pass = two_pass
        self._enable_punc = enable_punc
        self._enable_itn = enable_itn
        self._uid = uid
        self._hotwords = _clean_hotwords(hotwords)

        self._ws: ClientConnection | None = None
        self._connect_id = str(uuid.uuid4())
        self._request_id = str(uuid.uuid4())
        self.log_id: str | None = None

    async def connect(self) -> None:
        headers = {
            "X-Api-Key": self._api_key,
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Request-Id": self._request_id,
            "X-Api-Connect-Id": self._connect_id,
        }
        self._ws = await websockets.connect(
            ASR_WS_URL, additional_headers=headers, max_size=None
        )
        response_headers = getattr(self._ws, "response", None)
        if response_headers is not None:
            self.log_id = response_headers.headers.get("X-Tt-Logid")
            logger.info("doubao asr connected logid=%s", self.log_id)

        await self._send_full_client_request(self.request_payload())

    def request_payload(self) -> dict:
        """The initial "full client request" this client connects with."""
        payload = {
            "user": {"uid": self._uid},
            "audio": {
                "format": "pcm",
                "rate": self._sample_rate,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": self._enable_itn,
                "enable_punc": self._enable_punc,
                "enable_nonstream": self._two_pass,
                # Learners pause to find words. Keep the ASR's segment
                # window separate from the user-turn boundary (release).
                "end_window_size": 2000,
                "result_type": "full",
            },
        }
        if self._language:
            payload["audio"]["language"] = self._language
        if self._hotwords:
            payload["request"]["corpus"] = {
                "context": json.dumps(
                    {"hotwords": [{"word": w} for w in self._hotwords]},
                    ensure_ascii=False,
                )
            }
        return payload

    async def _send_full_client_request(self, payload: dict) -> None:
        assert self._ws is not None
        body = maybe_gzip(json.dumps(payload).encode("utf-8"))
        header = proto.build_header(
            proto.MSG_TYPE_FULL_CLIENT_REQUEST,
            proto.FLAGS_NO_SEQUENCE,
            proto.SERIALIZATION_JSON,
            proto.COMPRESSION_GZIP,
        )
        frame = header + proto.pack_u32(len(body)) + body
        await self._ws.send(frame)

    async def send_audio(self, pcm_chunk: bytes, *, is_last: bool = False) -> None:
        """Send one chunk of 16-bit mono PCM audio at the configured rate."""
        assert self._ws is not None
        body = maybe_gzip(pcm_chunk)
        flags = proto.FLAGS_LAST_NO_SEQUENCE if is_last else proto.FLAGS_NO_SEQUENCE
        header = proto.build_header(
            proto.MSG_TYPE_AUDIO_ONLY_REQUEST,
            flags,
            proto.SERIALIZATION_NONE,
            proto.COMPRESSION_GZIP,
        )
        frame = header + proto.pack_u32(len(body)) + body
        await self._ws.send(frame)

    async def responses(self) -> AsyncIterator[AsrResult | AsrErrorResult]:
        """Yield parsed responses until the connection closes or a last
        packet's response is received."""
        assert self._ws is not None
        async for raw in self._ws:
            if isinstance(raw, str):
                logger.warning("doubao asr: unexpected text frame: %s", raw)
                continue
            parsed = self._parse_message(raw)
            yield parsed
            if isinstance(parsed, AsrResult) and parsed.is_last:
                return

    def _parse_message(self, data: bytes) -> AsrResult | AsrErrorResult:
        header = proto.parse_header(data)
        offset = header.header_size_bytes

        if header.message_type == proto.MSG_TYPE_ERROR:
            code = proto.unpack_u32(data, offset)
            offset += 4
            msg_bytes, offset = proto.read_sized_field(data, offset)
            return AsrErrorResult(code=code, message=msg_bytes.decode("utf-8", "replace"))

        if header.message_type != proto.MSG_TYPE_FULL_SERVER_RESPONSE:
            raise DoubaoASRError(f"unexpected message type from server: {header.message_type:#b}")

        # "Full server response" carries a 4-byte sequence number before the
        # payload only when the flags say so. On this endpoint the very first
        # response — the connect ack carrying the log id — has no sequence,
        # and skipping four bytes anyway ate the payload's own length prefix
        # and left ``json.loads`` staring at the middle of a JSON object.
        #
        # The docs describe the *last* response as carrying a negative
        # sequence, but the docs' own worked example shows a positive one for
        # a response flagged as final — observed real traffic confirms the
        # flags nibble (not the sequence's sign) is what actually
        # distinguishes "this is the final response", so we key off
        # ``header.flags`` for that too.
        if header.flags & proto.FLAGS_SEQUENCE_BIT:
            proto.unpack_i32(data, offset)
            offset += 4
        payload_size = proto.unpack_u32(data, offset)
        offset += 4
        payload = data[offset : offset + payload_size]
        payload = proto.maybe_decompress(payload, header.compression)

        parsed = json.loads(payload) if payload else {}
        result = parsed.get("result") or {}
        text = result.get("text", "") if isinstance(result, dict) else ""
        is_last = header.flags in (proto.FLAGS_LAST_NO_SEQUENCE, proto.FLAGS_LAST_NEGATIVE_SEQUENCE)
        return AsrResult(text=text, is_last=is_last, raw=parsed, log_id=self.log_id)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None


def maybe_gzip(data: bytes) -> bytes:
    return proto.maybe_compress(data, proto.COMPRESSION_GZIP)
