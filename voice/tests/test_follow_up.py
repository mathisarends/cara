import asyncio
from collections.abc import AsyncIterable, AsyncIterator

from voice.audio import AudioBridge, AudioHub, AudioInput, AudioOutput
from voice.events import (
    FollowUpCountdown,
    FollowUpTimedOut,
    SessionEnded,
    SessionStarted,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing, VoiceTurnRequested
from voice.handler import FollowUpHandler
from voice.llm import AgentBridge, AgentEvent, TextDelta, TurnCompleted
from voice.pipeline import SpeechPipeline, TurnManager
from voice.stt import SpeechToText, Transcription, TranscriptionKind
from voice.tts import TextToSpeech, TextToSpeechBridge


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


class _SpeechToText(SpeechToText):
    """Transcribes the first turn and stays silent for every follow-up turn."""

    def __init__(self) -> None:
        self.calls = 0

    async def transcribe(
        self, audio: AsyncIterable[bytes]
    ) -> AsyncIterator[Transcription]:
        await anext(aiter(audio))
        self.calls += 1
        if self.calls > 1:
            await asyncio.sleep(3_600)
        yield Transcription("Hey Mycroft command", True, TranscriptionKind.END)


class _AgentSession:
    async def start_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        return self._stream_turn()

    async def _stream_turn(self) -> AsyncIterator[AgentEvent]:
        yield TextDelta("ok")
        yield TurnCompleted()

    async def steer(self, text: str) -> None:
        pass

    async def interrupt(self) -> None:
        pass


class _TextToSpeech(TextToSpeech):
    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        async for chunk in text:
            yield chunk.encode()


class _Output(AudioOutput):
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    @property
    def is_playing(self) -> bool:
        return False

    async def start(self, *, sample_rate: int, channels: int) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def play_chunk(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def finish_response(self) -> None:
        pass

    async def clear_buffer(self) -> None:
        pass


def test_a_finished_response_opens_a_follow_up_turn_without_a_wake_word() -> None:
    async def run() -> tuple[_SpeechToText, list[int], FollowUpTimedOut]:
        input_device = _Input()
        stt = _SpeechToText()
        event_bus = EventBus()
        audio_hub = AudioHub(input_device)
        AudioBridge(
            event_bus=event_bus,
            audio_hub=audio_hub,
            output_device=_Output(),
        )
        AgentBridge(event_bus=event_bus, session=_AgentSession())
        TextToSpeechBridge(
            event_bus=event_bus,
            text_to_speech=_TextToSpeech(),
        )
        pipeline = SpeechPipeline(
            wake_word_phrase="hey mycroft",
            speech_to_text=stt,
            event_bus=event_bus,
        )
        turns = TurnManager(
            audio_hub=audio_hub,
            pipeline=pipeline,
            event_bus=event_bus,
        )
        follow_up = FollowUpHandler(
            event_bus=event_bus, window_seconds=1.0, countdown_seconds=1
        )
        countdowns: list[int] = []
        timed_out_event = asyncio.get_running_loop().create_future()

        async def capture_countdown(event: FollowUpCountdown) -> None:
            countdowns.append(event.remaining_seconds)

        async def capture_timeout(event: FollowUpTimedOut) -> None:
            timed_out_event.set_result(event)

        event_bus.on(FollowUpCountdown, capture_countdown)
        event_bus.on(FollowUpTimedOut, capture_timeout)

        await event_bus.dispatch(SessionStarted())
        try:
            await event_bus.dispatch(VoiceTurnRequested(sequence=0))
            timed_out = await asyncio.wait_for(timed_out_event, timeout=5.0)
        finally:
            follow_up.close()
            await event_bus.dispatch(SessionEnded())
            await turns.close()
            await event_bus.dispatch(VoiceResourcesClosing())

        return stt, countdowns, timed_out

    stt, countdowns, timed_out = asyncio.run(run())

    assert stt.calls == 2
    assert countdowns == [1]
    assert timed_out.timeout_seconds == 1.0
