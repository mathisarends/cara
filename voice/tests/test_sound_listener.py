import asyncio

from transitbus import EventBus

from agent.events import SessionEnded
from voice.events import WakeWordDetected
from voice.events.listener import Earcon, SoundListener


class RecordingEarconPlayer:
    def __init__(self) -> None:
        self.earcons: list[Earcon] = []

    async def play(self, earcon: Earcon) -> None:
        self.earcons.append(earcon)


def test_wake_word_detected_plays_wake_earcon_before_dispatch_completes() -> None:
    async def run() -> list[Earcon]:
        event_bus = EventBus()
        earcons = RecordingEarconPlayer()
        SoundListener(event_bus, earcons)
        await event_bus.dispatch(
            WakeWordDetected(score=0.8, sequence=4, name="hey_mycroft")
        )
        return earcons.earcons

    assert asyncio.run(run()) == [Earcon.WAKE]


def test_session_ended_plays_sleep_earcon_before_dispatch_completes() -> None:
    async def run() -> list[Earcon]:
        event_bus = EventBus()
        earcons = RecordingEarconPlayer()
        SoundListener(event_bus, earcons)
        await event_bus.dispatch(SessionEnded())
        return earcons.earcons

    assert asyncio.run(run()) == [Earcon.SLEEP]
