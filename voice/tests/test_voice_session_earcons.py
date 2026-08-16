import asyncio
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path

from transitbus import EventBus

from agent.agent import Agent
from agent.tools import create_tools
from voice import VoiceSession
from voice.audio.output import AudioOutput, AudioPlayer, EarconPlayer
from voice.speech import SpeechInput, SpeechOutput, SpeechSettings
from voice.wakeword.ports import WakeWordSessionSource


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


class NoBargeIn:
    async def wait(self, *, cancel: asyncio.Event) -> None:
        await cancel.wait()


def test_first_recording_arms_after_wake_earcon(tmp_path: Path) -> None:
    async def run() -> list[str]:
        events: list[str] = []
        player = AudioPlayer(RecordingPlayer(events))
        event_bus = EventBus()
        speech_settings = SpeechSettings()
        session = VoiceSession(
            agent=Agent(
                llm=UnusedDependency(), tools=create_tools(), prompt_root=tmp_path
            ),
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
            barge_in=NoBargeIn(),
            event_bus=event_bus,
            earcons=EarconPlayer(player),
        )
        await session.run_once()
        return events

    assert asyncio.run(run())[:2] == ["play", "record"]
