"""In-memory test doubles for the voice-owned ports."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass
from uuid import uuid4

from voice.activation import Activation, ActivationSource
from voice.audio import (
    AudioDeviceFactory,
    AudioDevices,
    AudioFormat,
    AudioFrame,
    AudioInput,
    AudioOutput,
)
from voice.backend import (
    BackendAudio,
    BackendConnectionOptions,
    BackendEvent,
    BackendSessionState,
    StartedTurn,
    StartTurn,
    TurnRef,
    VoiceBackend,
    VoiceBackendConnector,
)
from voice.barge_in import BargeInSignal, BargeInStrategy
from voice.lifecycle import VoiceLifecycleEvent, VoiceLifecycleObserver

CHUNK = b"\x00\x00" * 1_280


async def settle() -> None:
    for _ in range(50):
        await asyncio.sleep(0)


@dataclass(frozen=True, slots=True)
class EndInput:
    turn: TurnRef
    next_sequence: int


@dataclass(frozen=True, slots=True)
class Interrupt:
    turn: TurnRef
    sequence: int | None


@dataclass(frozen=True, slots=True)
class PlaybackCompleted:
    turn: TurnRef


class FakeVoiceBackend(VoiceBackend):
    def __init__(self, initial_state: BackendSessionState | None = None) -> None:
        self._initial_state = initial_state or BackendSessionState()
        self._events: asyncio.Queue[BackendEvent | Exception | None] = asyncio.Queue()
        self._audio: asyncio.Queue[BackendAudio | Exception | None] = asyncio.Queue()
        self.start_requests: list[StartTurn] = []
        self.started_turns: list[TurnRef] = []
        self.inputs: list[tuple[TurnRef, int]] = []
        self.commands: list[EndInput | Interrupt | PlaybackCompleted] = []
        self.input_error: Exception | None = None
        self.close_calls = 0

    @property
    def input_format(self) -> AudioFormat:
        return AudioFormat(sample_rate=16_000)

    @property
    def output_format(self) -> AudioFormat:
        return AudioFormat(sample_rate=24_000)

    @property
    def initial_state(self) -> BackendSessionState:
        return self._initial_state

    def emit(self, event: BackendEvent | Exception | None) -> None:
        """Deliver an event; an exception fails the stream, ``None`` ends it."""
        self._events.put_nowait(event)

    def emit_audio(self, audio: BackendAudio | Exception | None) -> None:
        self._audio.put_nowait(audio)

    async def events(self) -> AsyncIterator[BackendEvent]:
        while (event := await self._events.get()) is not None:
            if isinstance(event, Exception):
                raise event
            yield event

    async def output_audio(self) -> AsyncIterator[BackendAudio]:
        while (audio := await self._audio.get()) is not None:
            if isinstance(audio, Exception):
                raise audio
            yield audio

    async def start_turn(self, request: StartTurn) -> StartedTurn:
        turn = TurnRef(uuid4())
        self.start_requests.append(request)
        self.started_turns.append(turn)
        return StartedTurn(turn=turn)

    async def send_input(self, turn: TurnRef, frame: AudioFrame) -> None:
        if self.input_error is not None:
            raise self.input_error
        self.inputs.append((turn, frame.sequence))

    async def end_input(self, turn: TurnRef, next_sequence: int) -> None:
        self.commands.append(EndInput(turn, next_sequence))

    async def interrupt(self, turn: TurnRef, sequence: int | None) -> None:
        self.commands.append(Interrupt(turn, sequence))

    async def playback_completed(self, turn: TurnRef) -> None:
        self.commands.append(PlaybackCompleted(turn))

    async def close(self) -> None:
        self.close_calls += 1


class FakeVoiceBackendConnector(VoiceBackendConnector):
    def __init__(self, backend: FakeVoiceBackend) -> None:
        self.backend = backend
        self.options: BackendConnectionOptions | None = None

    async def connect(self, options: BackendConnectionOptions) -> VoiceBackend:
        self.options = options
        return self.backend


class StreamingAudioInput(AudioInput):
    """A microphone whose chunks, failure and end the test controls."""

    def __init__(self) -> None:
        self._active = False
        self._chunks: asyncio.Queue[bytes | Exception | None] = asyncio.Queue()
        self.stop_calls = 0

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
        self.stop_calls += 1
        self._active = False
        self._chunks.put_nowait(None)

    def emit(self, chunk: bytes | Exception | None = CHUNK) -> None:
        self._chunks.put_nowait(chunk)

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        while self._active and (chunk := await self._chunks.get()) is not None:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


class RecordingAudioOutput(AudioOutput):
    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.clear_calls = 0
        self.stop_calls = 0

    @property
    def is_playing(self) -> bool:
        return False

    async def start(self, *, sample_rate: int, channels: int) -> None:
        pass

    async def stop(self) -> None:
        self.stop_calls += 1

    async def play_chunk(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def clear_buffer(self) -> None:
        self.clear_calls += 1


class FakeAudioDevices(AudioDeviceFactory):
    def __init__(self) -> None:
        self.input = StreamingAudioInput()
        self.output = RecordingAudioOutput()

    async def open(self, resources: AsyncExitStack) -> AudioDevices:
        return AudioDevices(input=self.input, output=self.output)


class ManualActivationSource(ActivationSource):
    def __init__(self) -> None:
        self._activations: asyncio.Queue[Activation | None] = asyncio.Queue()

    def activate(self, activation: Activation) -> None:
        self._activations.put_nowait(activation)

    def end(self) -> None:
        self._activations.put_nowait(None)

    async def activations(self) -> AsyncIterator[Activation]:
        while (activation := await self._activations.get()) is not None:
            yield activation


class ManualBargeIn(BargeInStrategy):
    def __init__(self) -> None:
        self._signals: asyncio.Queue[BargeInSignal] = asyncio.Queue()

    def signal(self, sequence: int) -> None:
        self._signals.put_nowait(BargeInSignal(sequence=sequence))

    async def signals(self) -> AsyncIterator[BargeInSignal]:
        while True:
            yield await self._signals.get()


class RecordingObserver(VoiceLifecycleObserver):
    def __init__(self) -> None:
        self.events: list[VoiceLifecycleEvent] = []

    async def on_lifecycle_event(self, event: VoiceLifecycleEvent) -> None:
        self.events.append(event)

    @property
    def names(self) -> list[str]:
        return [type(event).__name__ for event in self.events]
