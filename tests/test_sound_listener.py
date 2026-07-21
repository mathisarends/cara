import asyncio

from cara.audio import Earcon
from cara.events import AssistantState, EventBus, Interrupted, SessionEnded
from cara.listener import SoundListener


class RecordingEarconPlayer:
    def __init__(self) -> None:
        self.earcons: list[Earcon] = []

    async def play(self, earcon: Earcon) -> None:
        self.earcons.append(earcon)

    def play_soon(self, earcon: Earcon) -> None:
        self.earcons.append(earcon)


def test_interrupted_plays_interrupt_earcon_before_dispatch_completes() -> None:
    async def run() -> list[Earcon]:
        event_bus = EventBus()
        earcons = RecordingEarconPlayer()
        SoundListener(event_bus, earcons)
        await event_bus.dispatch(Interrupted(phase=AssistantState.SPEAKING))
        return earcons.earcons

    assert asyncio.run(run()) == [Earcon.INTERRUPT]


def test_session_ended_schedules_sleep_earcon() -> None:
    async def run() -> list[Earcon]:
        event_bus = EventBus()
        earcons = RecordingEarconPlayer()
        SoundListener(event_bus, earcons)
        await event_bus.dispatch(SessionEnded())
        return earcons.earcons

    assert asyncio.run(run()) == [Earcon.SLEEP]
