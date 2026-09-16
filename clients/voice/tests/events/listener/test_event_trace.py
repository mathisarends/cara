import asyncio
import logging
from uuid import UUID

from voice.events import (
    AssistantAudioChunk,
    SessionStarted,
    UserAudioChunk,
)
from voice.events.bus import EventBus
from voice.events.listener import EventTrace
from voice.events.models import VoiceTurnEnded, VoiceTurnStarted

_LOGGER = "voice.events.listener.event_trace"
_TURN_ID = UUID("1b3c84fa-0000-4000-8000-000000000000")


def test_the_trace_keeps_the_order_of_the_turn_lifecycle(caplog) -> None:
    async def run() -> None:
        event_bus = EventBus()
        EventTrace(event_bus)
        await event_bus.emit(SessionStarted())
        await event_bus.emit(VoiceTurnStarted(turn_id=_TURN_ID))
        await event_bus.emit(VoiceTurnEnded(turn_id=_TURN_ID))

    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        asyncio.run(run())

    assert caplog.messages == [
        "SessionStarted()",
        "VoiceTurnStarted(turn_id=1b3c84fa)",
        "VoiceTurnEnded(turn_id=1b3c84fa)",
    ]


def test_streamed_chunks_are_counted_instead_of_logged(caplog) -> None:
    async def run() -> None:
        event_bus = EventBus()
        EventTrace(event_bus)
        for sequence in range(3):
            await event_bus.emit(UserAudioChunk(sequence=sequence, chunk=b"\x00\x01"))
        for _ in range(2):
            await event_bus.emit(
                AssistantAudioChunk(turn_id=_TURN_ID, chunk=b"\x00\x01")
            )
        await event_bus.emit(VoiceTurnEnded(turn_id=_TURN_ID))

    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        asyncio.run(run())

    assert caplog.messages == [
        "UserAudioChunk x3",
        "AssistantAudioChunk x2",
        "VoiceTurnEnded(turn_id=1b3c84fa)",
    ]


def test_the_trace_costs_nothing_while_debug_logging_is_off(caplog) -> None:
    async def run() -> None:
        event_bus = EventBus()
        EventTrace(event_bus)
        await event_bus.emit(SessionStarted())

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        asyncio.run(run())

    assert caplog.messages == []
