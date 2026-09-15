import asyncio
import time
from collections.abc import AsyncIterator
from typing import Self
from urllib.parse import urljoin, urlparse, urlunparse

from websockets.asyncio.client import ClientConnection, connect

from voice.gateway.framing import MediaFrame, MediaFrameKind


class MediaTransport:
    def __init__(self, url: str, token: str) -> None:
        self._url = url
        self._token = token
        self._socket: ClientConnection | None = None
        self._send_lock = asyncio.Lock()
        self._closed = False

    @classmethod
    async def connect(cls, base_url: str, media_path: str, token: str) -> Self:
        transport = cls(_websocket_url(base_url, media_path), token)
        await transport._connect()
        return transport

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
        while not self._closed:
            socket = self._socket
            if socket is None:
                await self._connect()
                socket = self._socket
            if socket is None:
                return
            try:
                message = await socket.recv()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._socket = None
                if not self._closed:
                    await asyncio.sleep(0.25)
                continue
            if not isinstance(message, bytes):
                raise ValueError("Voice media socket received a text frame")
            frame = MediaFrame.decode(message)
            if frame.kind not in {
                MediaFrameKind.OUTPUT_PCM,
                MediaFrameKind.OUTPUT_END,
            }:
                raise ValueError("Gateway sent an input media frame")
            yield frame

    async def close(self) -> None:
        self._closed = True
        socket, self._socket = self._socket, None
        if socket is not None:
            await socket.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _connect(self) -> None:
        if self._closed:
            raise RuntimeError("Media transport is closed")
        self._socket = await connect(
            self._url,
            additional_headers={"Authorization": f"Bearer {self._token}"},
            compression=None,
            max_size=None,
        )

    async def _send(self, frame: MediaFrame) -> None:
        async with self._send_lock:
            socket = self._socket
            if socket is None:
                raise ConnectionError("Voice media socket is disconnected")
            await socket.send(frame.encode())


def _websocket_url(base_url: str, media_path: str) -> str:
    absolute = urljoin(f"{base_url.rstrip('/')}/", media_path.lstrip("/"))
    parsed = urlparse(absolute)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse(parsed._replace(scheme=scheme))
