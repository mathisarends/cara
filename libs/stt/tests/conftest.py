import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel


class ConnectedMessage(BaseModel):
    type: str = "Connected"
    request_id: str
    sequence_id: int = 0


class TurnInfoMessage(BaseModel):
    type: str = "TurnInfo"
    request_id: str = "request-id"
    sequence_id: int = 0
    event: str
    turn_index: int = 0
    transcript: str = ""
    words: list[dict[str, Any]] = []
    end_of_turn_confidence: float = 0.5


class FatalErrorMessage(BaseModel):
    type: str = "FatalError"
    sequence_id: int = 0
    code: str
    description: str


class FakeConnection:
    def __init__(
        self, messages: list[Any], send_error: Exception | None = None
    ) -> None:
        self.messages = messages
        self.send_error = send_error
        self.audio: list[bytes] = []
        self.controls: list[Any] = []
        self.closed = False

    async def send_media(self, chunk: bytes) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.audio.append(chunk)

    async def send_control(self, message: Any) -> None:
        self.controls.append(message)

    async def __aiter__(self) -> AsyncIterator[Any]:
        for message in self.messages:
            await asyncio.sleep(0)
            yield message


class FakeConnectionManager:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self._connection

    async def __aexit__(self, *args: object) -> None:
        self._connection.closed = True


class FakeListenV2:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.calls: list[dict[str, Any]] = []

    def connect(self, **kwargs: Any) -> FakeConnectionManager:
        self.calls.append(kwargs)
        return FakeConnectionManager(self.connection)


class FakeDeepgramClient:
    def __init__(self, connection: FakeConnection) -> None:
        self.v2 = FakeListenV2(connection)
        self.listen = SimpleNamespace(v2=self.v2)


@pytest.fixture
def audio_stream():
    async def stream(*chunks: bytes) -> AsyncIterator[bytes]:
        for chunk in chunks:
            yield chunk

    return stream
