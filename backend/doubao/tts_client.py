"""Raw asyncio client for Volcengine's bidirectional streaming TTS.

Doc: https://docs.volcengine.com/docs/6561/1329505
("语音合成大模型 - WebSocket 双向流式-V3", fetched 2026-08-11)

Protocol summary (see ``app/doubao/protocol.py`` for the shared 4-byte
header): every frame after the header carries a 4-byte big-endian ``event``
number, then — depending on the event — a size-prefixed ``connect_id``
(connection-class events) or ``session_id`` (session/data-class events),
then a size-prefixed payload (JSON for control messages, raw bytes for
audio).

One WebSocket connection can be reused for many sequential sessions (one
session per synthesized turn): ``StartConnection`` once, then per turn
``StartSession`` -> one or more ``TaskRequest`` (text) -> ``FinishSession``,
waiting for ``SessionFinished`` before starting the next session on the same
connection.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import websockets
from websockets.asyncio.client import ClientConnection

from . import protocol as proto

logger = logging.getLogger(__name__)

TTS_WS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"

EVENT_START_CONNECTION = 1
EVENT_FINISH_CONNECTION = 2
EVENT_CONNECTION_STARTED = 50
EVENT_CONNECTION_FAILED = 51
EVENT_CONNECTION_FINISHED = 52
EVENT_START_SESSION = 100
EVENT_CANCEL_SESSION = 101
EVENT_FINISH_SESSION = 102
EVENT_SESSION_STARTED = 150
EVENT_SESSION_CANCELED = 151
EVENT_SESSION_FINISHED = 152
EVENT_SESSION_FAILED = 153
EVENT_TASK_REQUEST = 200
EVENT_TTS_SENTENCE_START = 350
EVENT_TTS_SENTENCE_END = 351
EVENT_TTS_RESPONSE = 352

_CONNECTION_EVENTS = {
    EVENT_START_CONNECTION,
    EVENT_FINISH_CONNECTION,
    EVENT_CONNECTION_STARTED,
    EVENT_CONNECTION_FAILED,
    EVENT_CONNECTION_FINISHED,
}


@dataclass
class TTSMessage:
    event: int
    session_id: str | None = None
    connect_id: str | None = None
    json_payload: dict | None = None
    audio: bytes | None = None
    raw: bytes = field(default=b"", repr=False)


class DoubaoTTSError(RuntimeError):
    pass


class DoubaoTTSClient:
    """One WebSocket connection to Doubao's bidirectional TTS, supporting
    multiple sequential sessions (one per synthesized reply)."""

    def __init__(
        self,
        *,
        api_key: str,
        resource_id: str = "seed-tts-2.0",
        speaker: str = "zh_female_shuangkuaisisi_moon_bigtts",
        sample_rate: int = 24000,
        audio_format: str = "pcm",
        speech_rate: int = 0,
    ):
        self._api_key = api_key
        self._resource_id = resource_id
        self._speaker = speaker
        self._sample_rate = sample_rate
        self._audio_format = audio_format
        # Volcengine speech_rate: [-50, 100], 0 being normal speed. Slower
        # input is easier to follow at low proficiency, and a tutor the
        # learner cannot follow is a tutor they answer at random.
        self._speech_rate = max(-50, min(100, int(speech_rate)))

        self._ws: ClientConnection | None = None
        self._connect_id = str(uuid.uuid4())
        self.log_id: str | None = None
        self._current_session_id: str | None = None

    async def connect(self) -> None:
        headers = {
            "X-Api-Key": self._api_key,
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Connect-Id": self._connect_id,
        }
        self._ws = await websockets.connect(
            TTS_WS_URL, additional_headers=headers, max_size=None
        )
        response = getattr(self._ws, "response", None)
        if response is not None:
            self.log_id = response.headers.get("X-Tt-Logid")
            logger.info("doubao tts connected logid=%s", self.log_id)

        await self._send_control_frame(EVENT_START_CONNECTION, payload={})
        msg = await self._recv_one()
        if msg.event != EVENT_CONNECTION_STARTED:
            raise DoubaoTTSError(f"expected ConnectionStarted, got event={msg.event} {msg.json_payload}")

    async def start_session(self, *, text_speaker: str | None = None) -> str:
        """Start a new synthesis session on the existing connection and
        return its session_id. Call ``send_text`` / ``finish_session``
        afterwards."""
        assert self._ws is not None
        session_id = str(uuid.uuid4())
        self._current_session_id = session_id
        payload = {
            "user": {"uid": "saywith-voice-gateway"},
            "event": EVENT_START_SESSION,
            "req_params": {
                "speaker": text_speaker or self._speaker,
                "audio_params": {
                    "format": self._audio_format,
                    "sample_rate": self._sample_rate,
                    "speech_rate": self._speech_rate,
                },
            },
        }
        await self._send_control_frame(EVENT_START_SESSION, session_id=session_id, payload=payload)
        return session_id

    async def send_text(self, session_id: str, text: str) -> None:
        payload = {"req_params": {"text": text}}
        await self._send_control_frame(EVENT_TASK_REQUEST, session_id=session_id, payload=payload)

    async def finish_session(self, session_id: str) -> None:
        await self._send_control_frame(EVENT_FINISH_SESSION, session_id=session_id, payload={})

    async def cancel_session(self, session_id: str) -> None:
        await self._send_control_frame(EVENT_CANCEL_SESSION, session_id=session_id, payload={})

    async def finish_connection(self) -> None:
        await self._send_control_frame(EVENT_FINISH_CONNECTION, payload={})

    async def _send_control_frame(
        self, event: int, *, session_id: str | None = None, payload: dict
    ) -> None:
        assert self._ws is not None
        body = json.dumps(payload).encode("utf-8")
        header = proto.build_header(
            proto.MSG_TYPE_FULL_CLIENT_REQUEST,
            proto.FLAGS_WITH_EVENT,
            proto.SERIALIZATION_JSON,
            proto.COMPRESSION_NONE,
        )
        frame = bytearray(header)
        frame += proto.pack_i32(event)
        if session_id is not None:
            sid = session_id.encode("utf-8")
            frame += proto.pack_u32(len(sid))
            frame += sid
        frame += proto.pack_u32(len(body))
        frame += body
        await self._ws.send(bytes(frame))

    async def messages(self) -> AsyncIterator[TTSMessage]:
        """Yield every parsed message until the underlying connection
        closes. Callers filter by ``.event``."""
        assert self._ws is not None
        async for raw in self._ws:
            if isinstance(raw, str):
                logger.warning("doubao tts: unexpected text frame: %s", raw)
                continue
            yield self._parse_message(raw)

    async def _recv_one(self) -> TTSMessage:
        assert self._ws is not None
        raw = await self._ws.recv()
        if isinstance(raw, str):
            raise DoubaoTTSError(f"unexpected text frame while waiting for control message: {raw}")
        return self._parse_message(raw)

    def _parse_message(self, data: bytes) -> TTSMessage:
        header = proto.parse_header(data)
        offset = header.header_size_bytes

        if header.message_type == proto.MSG_TYPE_ERROR:
            code = proto.unpack_u32(data, offset)
            offset += 4
            payload_bytes, offset = proto.read_sized_field(data, offset)
            try:
                payload = json.loads(payload_bytes) if payload_bytes else {}
            except json.JSONDecodeError:
                payload = {"raw": payload_bytes.decode("utf-8", "replace")}
            payload["_error_code"] = code
            return TTSMessage(event=-1, json_payload=payload, raw=data)

        event = proto.unpack_i32(data, offset)
        offset += 4

        connect_id = None
        session_id = None
        if event in _CONNECTION_EVENTS and event != EVENT_START_CONNECTION and event != EVENT_FINISH_CONNECTION:
            cid_bytes, offset = proto.read_sized_field(data, offset)
            connect_id = cid_bytes.decode("utf-8", "replace")
        elif event not in (EVENT_START_CONNECTION, EVENT_FINISH_CONNECTION) and offset + 4 <= len(data):
            # Session/data-class events (100+) carry a session_id field.
            sid_bytes, offset = proto.read_sized_field(data, offset)
            session_id = sid_bytes.decode("utf-8", "replace")

        payload_size = proto.unpack_u32(data, offset)
        offset += 4
        payload_bytes = data[offset : offset + payload_size]
        payload_bytes = proto.maybe_decompress(payload_bytes, header.compression)

        if header.message_type == proto.MSG_TYPE_AUDIO_ONLY_RESPONSE:
            return TTSMessage(
                event=event, session_id=session_id, connect_id=connect_id, audio=payload_bytes, raw=data
            )

        json_payload: dict | None = None
        if payload_bytes:
            try:
                json_payload = json.loads(payload_bytes)
            except json.JSONDecodeError:
                logger.warning("doubao tts: non-JSON payload for event=%s", event)
        return TTSMessage(
            event=event, session_id=session_id, connect_id=connect_id, json_payload=json_payload, raw=data
        )

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
