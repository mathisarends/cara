import asyncio
import time
from collections.abc import AsyncIterator

from gateway_rpc_client import BinaryChannel
from voice.gateway.framing import MediaFrame, MediaFrameKind


class MediaTransport:
    def __init__(self, channel: BinaryChannel) -> None:
        self._channel = channel
        self._send_lock = asyncio.Lock()
        self._closed = False

    async def send_input(
        self,
        turn_index: int,
        sequence: int,
        payload: bytes,
    ) -> None:
        frame = MediaFrame(
            MediaFrameKind.INPUT_PCM,
            turn_index,
            sequence,
            time.time_ns() // 1_000_000,
            payload,
        )
        await self._send(frame)

    async def end_input(self, turn_index: int, sequence: int) -> None:
        frame = MediaFrame(
            MediaFrameKind.INPUT_END,
            turn_index,
            sequence,
            time.time_ns() // 1_000_000,
        )
        await self._send(frame)

    async def frames(self) -> AsyncIterator[MediaFrame]:
        async for payload in self._channel:
            frame = MediaFrame.decode(payload)
            if frame.kind not in {
                MediaFrameKind.OUTPUT_PCM,
                MediaFrameKind.OUTPUT_END,
            }:
                raise ValueError("Gateway sent an input media frame")
            yield frame

    async def close(self) -> None:
        self._closed = True
        await self._channel.close()

    async def _send(self, frame: MediaFrame) -> None:
        async with self._send_lock:
            if self._closed:
                raise ConnectionError("Voice media socket is disconnected")
            await self._channel.send(frame.encode())
