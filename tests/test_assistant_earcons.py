import asyncio

from cara.assistant import VoiceAssistant
from cara.events import EventBus
from cara.wakeword import WakeWordSettings


class RecordingPlayer:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        self._events.append("play")


class EmptyRecorder:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
        speech_started: asyncio.Event | None = None,
        cancel: asyncio.Event | None = None,
    ) -> bytes | None:
        self._events.append("record")
        return None


class UnusedDependency:
    pass


def test_wake_earcon_finishes_before_first_recording() -> None:
    async def run() -> list[str]:
        events: list[str] = []
        assistant = VoiceAssistant(
            llm=UnusedDependency(),
            recorder=EmptyRecorder(events),
            player=RecordingPlayer(events),
            stt=UnusedDependency(),
            tts=UnusedDependency(),
            event_bus=EventBus(),
            wake_word_settings=WakeWordSettings(),
        )
        await assistant._run()
        return events

    assert asyncio.run(run())[:2] == ["play", "record"]
