import asyncio
import threading

from cara.assistant import VoiceAssistant
from cara.audio import AudioOutput, AudioPlayer
from cara.events import EventBus
from cara.wakeword import WakeWordSettings
from cara.wakeword.ports import WakeWordDetectionSource


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
    ) -> bytes | None:
        while ready is not None and not ready.is_set():
            await asyncio.sleep(0)
        self._events.append("record")
        return None


class UnusedDependency:
    pass


class NoWakeWordListener(WakeWordDetectionSource):
    async def detect_once(self, *, cancel: asyncio.Event | None = None) -> float | None:
        assert cancel is not None
        await cancel.wait()
        return None


def test_first_recording_arms_after_wake_earcon() -> None:
    async def run() -> list[str]:
        events: list[str] = []
        assistant = VoiceAssistant(
            llm=UnusedDependency(),
            recorder=EmptyRecorder(events),
            player=AudioPlayer(RecordingPlayer(events)),
            stt=UnusedDependency(),
            tts=UnusedDependency(),
            event_bus=EventBus(),
            wake_word_settings=WakeWordSettings(),
        )
        await assistant._run(NoWakeWordListener())
        return events

    assert asyncio.run(run())[:2] == ["play", "record"]
