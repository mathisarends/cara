import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from hueify import GroupedLight, Room
from hueify.models import GroupArchetype, GroupMetadata, HueEvent

from voice import HueObserver
from voice.events import (
    AssistantSpeechStarted,
    AssistantToolCompleted,
    AssistantToolStarted,
    AssistantTurnStarted,
    SessionEnded,
    UserTurnStarted,
    WakeWordDetected,
)
from voice.events.bus import EventBus
from voice.events.models import Event
from voice.observer import _ObserverBridge

_ROOM_ID = UUID("00000000-0000-0000-0000-000000000001")
_GROUPED_LIGHT_ID = UUID("00000000-0000-0000-0000-000000000002")


class _RecordingRooms:
    def __init__(self) -> None:
        self.room = Room(
            id=_ROOM_ID,
            metadata=GroupMetadata(name="Test room", archetype=GroupArchetype.BEDROOM),
            services=[],
        )
        self.grouped_light_state = GroupedLight(
            id=_GROUPED_LIGHT_ID,
            on={"on": True},
            dimming={"brightness": 50},
            color_temperature={"mirek": 292},
        )
        self.changes: list[tuple[float, int | None, float]] = []

    async def find_by_name(self, name: str) -> Room:
        assert name == "Test room"
        return self.room

    async def grouped_light(self, room_id: UUID) -> GroupedLight:
        assert room_id == _ROOM_ID
        return self.grouped_light_state

    async def set_state(
        self,
        room_id: UUID,
        *,
        on: bool,
        brightness: float,
        mirek: int | None,
        transition: float,
    ) -> None:
        assert room_id == _ROOM_ID
        assert on is True
        self.changes.append((brightness, mirek, transition))


class _RecordingHue:
    def __init__(self) -> None:
        self.rooms = _RecordingRooms()
        self.stream_started = False
        self.closed = False
        self._handlers: dict[str, Callable[[HueEvent], Awaitable[object]]] = {}

    def on(
        self,
        event_type: str,
        handler: Callable[[HueEvent], Awaitable[object]],
    ) -> None:
        self._handlers[event_type] = handler

    def off(
        self,
        event_type: str,
        handler: Callable[[HueEvent], Awaitable[object]],
    ) -> None:
        assert self._handlers[event_type] == handler
        del self._handlers[event_type]

    async def start_stream(self) -> None:
        self.stream_started = True

    async def close(self) -> None:
        self.closed = True


async def _dispatch_and_drain(
    event_bus: EventBus, observer: HueObserver, event: Event
) -> None:
    await event_bus.dispatch(event)
    await asyncio.wait_for(observer._jobs.join(), timeout=1)


def test_hue_observer_reflects_voice_turn_and_tool_lifecycle() -> None:
    async def run() -> _RecordingHue:
        event_bus = EventBus()
        hue = _RecordingHue()
        observer = HueObserver(room_name="Test room", hue=hue)
        bridge = _ObserverBridge(event_bus=event_bus, observers=(observer,))
        bridge.setup()
        await bridge.prepare()

        assert hue.rooms.changes == []
        await _dispatch_and_drain(
            event_bus,
            observer,
            WakeWordDetected(score=0.9, sequence=1, name="hey_mycroft"),
        )
        await _dispatch_and_drain(event_bus, observer, UserTurnStarted())
        await _dispatch_and_drain(event_bus, observer, AssistantTurnStarted())
        await _dispatch_and_drain(event_bus, observer, AssistantSpeechStarted())
        await _dispatch_and_drain(
            event_bus,
            observer,
            AssistantToolStarted(turn_id=1, name="weather"),
        )
        await _dispatch_and_drain(
            event_bus,
            observer,
            AssistantToolCompleted(turn_id=1, name="weather"),
        )
        await _dispatch_and_drain(
            event_bus,
            observer,
            AssistantToolStarted(turn_id=1, name="calendar"),
        )
        await _dispatch_and_drain(
            event_bus,
            observer,
            AssistantToolStarted(turn_id=1, name="mail"),
        )
        await _dispatch_and_drain(
            event_bus,
            observer,
            AssistantToolCompleted(turn_id=1, name="calendar"),
        )
        await _dispatch_and_drain(
            event_bus,
            observer,
            AssistantToolCompleted(turn_id=1, name="mail"),
        )
        await event_bus.dispatch(SessionEnded())
        return hue

    hue = asyncio.run(run())

    assert hue.stream_started is True
    assert hue.closed is True
    assert hue.rooms.changes == [
        (58.0, 275, 0.2),
        (47.0, 309, 0.4),
        (50.0, 292, 0.5),
    ]


def test_hue_observer_preserves_external_changes_in_its_baseline() -> None:
    async def run() -> list[tuple[float, int | None, float]]:
        event_bus = EventBus()
        hue = _RecordingHue()
        observer = HueObserver(room_name="Test room", hue=hue)
        bridge = _ObserverBridge(event_bus=event_bus, observers=(observer,))
        bridge.setup()
        await bridge.prepare()

        await _dispatch_and_drain(event_bus, observer, UserTurnStarted())
        await observer._on_bridge_event(
            HueEvent.model_validate(
                {
                    "id": _GROUPED_LIGHT_ID,
                    "type": "grouped_light",
                    "dimming": {"brightness": 75},
                    "color_temperature": {"mirek": 250},
                }
            )
        )
        await event_bus.dispatch(SessionEnded())
        return hue.rooms.changes

    assert asyncio.run(run()) == [(58.0, 275, 0.2), (67.0, 267, 0.5)]
