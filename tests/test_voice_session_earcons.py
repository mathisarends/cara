import asyncio
import threading
from collections.abc import Awaitable, Callable

from transitbus import EventBus

from cara.agent import Agent
from cara.audio import AudioOutput, AudioPlayer, EarconPlayer
from cara.sessions import VoiceSession
from cara.speech import SpeechInput, SpeechOutput, SpeechSettings
from cara.tools import create_tools
from cara.wakeword.ports import WakeWordSessionSource


class RecordingPlayer:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    @property
    def output(self) -> AudioOutput:
        return AudioOutput.LOCAL

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        self._events.append("play")


class EmptyRecorder:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
        ready: threading.Event | None = None,
        on_speech_started: Callable[[], Awaitable[None]] | None = None,
    ) -> bytes | None:
        while ready is not None and not ready.is_set():
            await asyncio.sleep(0)
        self._events.append("record")
        return None


class UnusedDependency:
    pass


class NoWakeWordListener(WakeWordSessionSource):
    async def detections(self):
        yield 0.0

    async def detect_once(self, *, cancel: asyncio.Event | None = None) -> float | None:
        assert cancel is not None
        await cancel.wait()
        return None


def test_first_recording_arms_after_wake_earcon() -> None:
    async def run() -> list[str]:
        events: list[str] = []
        player = AudioPlayer(RecordingPlayer(events))
        event_bus = EventBus()
        speech_settings = SpeechSettings()
        session = VoiceSession(
            agent=Agent(llm=UnusedDependency(), tools=create_tools()),
            speech_input=SpeechInput(
                EmptyRecorder(events),
                UnusedDependency(),
                speech_settings,
                event_bus,
            ),
            speech_output=SpeechOutput(
                UnusedDependency(),
                player,
                speech_settings,
                event_bus,
            ),
            wake_word_listener=NoWakeWordListener(),
            event_bus=event_bus,
            earcons=EarconPlayer(player),
        )
        await session.run_once()
        return events

    assert asyncio.run(run())[:2] == ["play", "record"]
