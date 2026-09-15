from collections.abc import AsyncIterator, Callable

import numpy as np
import pytest

from voice.audio.ports import AudioInput, AudioOutput
from voice.events.bus import EventBus


class _AudioInput(AudioInput):
    def __init__(self) -> None:
        self._active = False
        self.stopped = False

    @property
    def sample_rate(self) -> int:
        return 16_000

    @property
    def channels(self) -> int:
        return 1

    @property
    def frames_per_chunk(self) -> int:
        return 1_280

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self) -> None:
        self._active = True

    async def stop(self) -> None:
        self._active = False
        self.stopped = True

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        if False:
            yield b""


class _AudioOutput(AudioOutput):
    def __init__(self) -> None:
        self._playing = False
        self.stopped = False

    @property
    def is_playing(self) -> bool:
        return self._playing

    async def start(self, *, sample_rate: int, channels: int) -> None:
        self._playing = True

    async def stop(self) -> None:
        self._playing = False
        self.stopped = True

    async def play_chunk(self, chunk: bytes) -> None:
        pass

    async def clear_buffer(self) -> None:
        pass


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def audio_input() -> AudioInput:
    return _AudioInput()


@pytest.fixture
def audio_output() -> AudioOutput:
    return _AudioOutput()


@pytest.fixture
def pcm() -> Callable[..., bytes]:
    def encode(*samples: int) -> bytes:
        return np.asarray(samples, dtype="<i2").tobytes()

    return encode
