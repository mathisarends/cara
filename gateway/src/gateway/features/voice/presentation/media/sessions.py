import asyncio
from dataclasses import dataclass
from uuid import UUID

from fastapi_rpckit import RpcBinaryOutput, RpcConnection, RpcConnectionClose

from gateway.features.voice.application import MediaSessions
from gateway.features.voice.presentation.media.framing import MediaFrame, MediaFrameKind


@dataclass(slots=True)
class _Connection:
    connection: RpcConnection
    output: RpcBinaryOutput
    send_lock: asyncio.Lock


class InMemoryMediaSessions(MediaSessions):
    def __init__(self) -> None:
        self._connections: dict[UUID, _Connection] = {}
        self._lock = asyncio.Lock()

    def connected(self, voice_session_id: UUID) -> bool:
        return voice_session_id in self._connections

    async def connect(
        self,
        voice_session_id: UUID,
        connection: RpcConnection,
        output: RpcBinaryOutput,
    ) -> bool:
        async with self._lock:
            if voice_session_id in self._connections:
                return False
            self._connections[voice_session_id] = _Connection(
                connection,
                output,
                asyncio.Lock(),
            )
            return True

    async def release(
        self,
        voice_session_id: UUID,
        connection: RpcConnection,
    ) -> None:
        async with self._lock:
            current = self._connections.get(voice_session_id)
            if current is not None and current.connection is connection:
                self._connections.pop(voice_session_id, None)

    async def disconnect(self, voice_session_id: UUID) -> None:
        async with self._lock:
            connection = self._connections.pop(voice_session_id, None)
        if connection is not None:
            await connection.connection.close(RpcConnectionClose.NORMAL)

    async def send(self, voice_session_id: UUID, frame: MediaFrame) -> None:
        connection = self._connections.get(voice_session_id)
        if connection is None:
            raise RuntimeError(f"Voice session {voice_session_id} is not connected")
        async with connection.send_lock:
            await connection.output.send(frame.encode())

    async def send_audio(
        self,
        voice_session_id: UUID,
        voice_turn_index: int,
        sequence: int,
        timestamp_ms: int,
        payload: bytes,
        *,
        end: bool = False,
    ) -> None:
        kind = MediaFrameKind.OUTPUT_END if end else MediaFrameKind.OUTPUT_PCM
        frame = MediaFrame(kind, voice_turn_index, sequence, timestamp_ms, payload)
        await self.send(voice_session_id, frame)
