from collections.abc import AsyncIterable, AsyncIterator, Callable

import numpy as np
import pytest

from voice.audio.ports import AudioInput, AudioOutput
from voice.events.bus import EventBus
from voice.llm.events import AgentEvent, TurnCompleted
from voice.stt import SpeechToText, Transcription
from voice.tts import TextToSpeech


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


class _SpeechToText(SpeechToText):
    def __init__(self) -> None:
        self.closed = False

    async def transcribe(
        self, audio: AsyncIterable[bytes]
    ) -> AsyncIterator[Transcription]:
        if False:
            yield Transcription(text="", is_final=False)

    async def aclose(self) -> None:
        self.closed = True


class _TextToSpeech(TextToSpeech):
    def __init__(self) -> None:
        self.closed = False

    @property
    def sample_rate(self) -> int:
        return 24_000

    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        if False:
            yield b""

    async def aclose(self) -> None:
        self.closed = True


class _AgentSession:
    async def prepare_turn(self) -> None:
        pass

    async def start_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        if False:
            yield TurnCompleted()

    async def steer(self, text: str) -> None:
        pass

    async def finish_turn(self) -> None:
        pass

    async def interrupt(self) -> None:
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
def speech_to_text() -> SpeechToText:
    return _SpeechToText()


@pytest.fixture
def text_to_speech() -> TextToSpeech:
    return _TextToSpeech()


@pytest.fixture
def agent_session() -> _AgentSession:
    return _AgentSession()


@pytest.fixture
def pcm() -> Callable[..., bytes]:
    def encode(*samples: int) -> bytes:
        return np.asarray(samples, dtype="<i2").tobytes()

    return encode
