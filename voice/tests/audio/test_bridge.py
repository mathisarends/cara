import asyncio
from collections.abc import AsyncIterator

from voice.audio import AudioBridge, AudioHub, AudioInput, AudioOutput
from voice.events import (
    AssistantAudioChunk,
    AssistantAudioCompleted,
    AssistantAudioStarted,
    AssistantPlaybackCompleted,
    AssistantSpeechStarted,
    SessionStarted,
    VoiceTurnFailed,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing


class _Input(AudioInput):
    def __init__(self) -> None:
        self._active = False

    @property
    def sample_rate(self) -> int:
        return 16_000

    @property
    def channels(self) -> int:
        return 1

    @property
    def frames_per_chunk(self) -> int:
        return 1280

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self) -> None:
        self._active = True

    async def stop(self) -> None:
        self._active = False

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        while self._active:
            yield bytes(2_560)
            await asyncio.sleep(0)


class _Output(AudioOutput):
    def __init__(self) -> None:
        self.started_with: tuple[int, int] | None = None
        self.chunks: list[bytes] = []
        self.finish_started = asyncio.Event()
        self.release_finish = asyncio.Event()
        self.stopped = False
        self.cleared = False

    @property
    def is_playing(self) -> bool:
        return self.finish_started.is_set() and not self.release_finish.is_set()

    async def start(self, *, sample_rate: int, channels: int) -> None:
        self.started_with = sample_rate, channels

    async def stop(self) -> None:
        self.stopped = True

    async def play_chunk(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def finish_response(self) -> None:
        self.finish_started.set()
        await self.release_finish.wait()

    async def clear_buffer(self) -> None:
        self.cleared = True


class _FailingOutput(_Output):
    async def play_chunk(self, chunk: bytes) -> None:
        raise RuntimeError("speaker disconnected")


def test_bridge_publishes_playback_completion_after_the_output_finishes() -> None:
    async def run() -> tuple[_Output, list[str], bool]:
        event_bus = EventBus()
        output = _Output()
        AudioBridge(
            event_bus=event_bus,
            audio_hub=AudioHub(_Input()),
            output_device=output,
        )
        lifecycle: list[str] = []

        async def speech_started(_: AssistantSpeechStarted) -> None:
            lifecycle.append("speech-started")

        async def playback_completed(_: AssistantPlaybackCompleted) -> None:
            lifecycle.append("playback-completed")

        event_bus.on(AssistantSpeechStarted, speech_started)
        event_bus.on(AssistantPlaybackCompleted, playback_completed)

        await event_bus.dispatch(SessionStarted())
        await event_bus.dispatch(AssistantAudioStarted(turn_id=7, sample_rate=24_000))
        await event_bus.dispatch(AssistantAudioChunk(turn_id=7, chunk=b"pcm"))
        completion = asyncio.create_task(
            event_bus.dispatch(AssistantAudioCompleted(turn_id=7))
        )
        await asyncio.wait_for(output.finish_started.wait(), timeout=1.0)
        completed_too_early = "playback-completed" in lifecycle
        output.release_finish.set()
        await completion
        await event_bus.dispatch(VoiceResourcesClosing())
        return output, lifecycle, completed_too_early

    output, lifecycle, completed_too_early = asyncio.run(run())

    assert output.started_with == (24_000, 1)
    assert output.chunks == [b"pcm"]
    assert lifecycle == ["speech-started", "playback-completed"]
    assert completed_too_early is False
    assert output.stopped is True


def test_bridge_reports_output_failure_without_blocking_the_pipeline() -> None:
    async def run() -> VoiceTurnFailed:
        event_bus = EventBus()
        AudioBridge(
            event_bus=event_bus,
            audio_hub=AudioHub(_Input()),
            output_device=_FailingOutput(),
            playback_queue_size=1,
        )
        failure = asyncio.get_running_loop().create_future()

        async def capture_failure(event: VoiceTurnFailed) -> None:
            failure.set_result(event)

        event_bus.on(VoiceTurnFailed, capture_failure)
        await event_bus.dispatch(SessionStarted())
        await event_bus.dispatch(AssistantAudioStarted(turn_id=3, sample_rate=24_000))
        await event_bus.dispatch(AssistantAudioChunk(turn_id=3, chunk=b"pcm"))
        await asyncio.wait_for(
            event_bus.dispatch(AssistantAudioCompleted(turn_id=3)), timeout=1.0
        )
        event = await asyncio.wait_for(failure, timeout=1.0)
        await event_bus.dispatch(VoiceResourcesClosing())
        return event

    event = asyncio.run(run())

    assert event.turn_id == 3
    assert event.message == "speaker disconnected"
