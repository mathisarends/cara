import asyncio

import pytest

from voice.events import SessionEnded, UserTranscriptionRequested, UserTurnStarted
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded, VoiceTurnRequested
from voice.handler import TurnCoordinator, TurnListener


def test_turn_coordinator_tracks_turns_without_an_event_bus() -> None:
    coordinator = TurnCoordinator()

    first_turn_id = coordinator.start_turn()

    assert first_turn_id == 1
    assert coordinator.has_active_turn
    assert coordinator.end_turn(first_turn_id)
    assert not coordinator.has_active_turn
    assert coordinator.start_turn() == 2


def test_turn_coordinator_rejects_overlapping_turns() -> None:
    coordinator = TurnCoordinator()
    coordinator.start_turn()

    with pytest.raises(RuntimeError, match="another is active"):
        coordinator.start_turn()


def test_turn_listener_maps_events_to_coordinator() -> None:
    async def run() -> tuple[TurnCoordinator, list[object]]:
        event_bus = EventBus()
        coordinator = TurnCoordinator()
        TurnListener(event_bus=event_bus, coordinator=coordinator)
        events: list[object] = []

        async def capture_started(event: UserTurnStarted) -> None:
            events.append(event)

        async def transcribe(event: UserTranscriptionRequested) -> None:
            events.append(event)

        async def capture_ended(event: VoiceTurnEnded) -> None:
            events.append(event)

        event_bus.on(UserTurnStarted, capture_started)
        event_bus.on_request(UserTranscriptionRequested, transcribe)
        event_bus.on(VoiceTurnEnded, capture_ended)

        await event_bus.request(VoiceTurnRequested(sequence=12))
        while coordinator.has_active_turn:
            await asyncio.sleep(0)
        await event_bus.dispatch(SessionEnded())
        return coordinator, events

    coordinator, events = asyncio.run(run())

    assert coordinator.is_closed
    assert events == [
        UserTurnStarted(),
        UserTranscriptionRequested(
            turn_id=1,
            sequence=12,
            pre_roll_seconds=0.16,
            speech_start_timeout=8.0,
        ),
        VoiceTurnEnded(turn_id=1),
    ]
