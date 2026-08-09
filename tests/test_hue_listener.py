import asyncio
from uuid import UUID

from hueify import GroupedLight, Room
from hueify.models import GroupArchetype, GroupMetadata, HueEvent
from transitbus import Event, EventBus

from cara.events import (
    AssistantTurnStarted,
    SessionEnded,
    SessionStarted,
    ToolCallFinished,
    ToolCallStarted,
    UserTurnStarted,
)
from cara.listener import HueListener

_ROOM_ID = UUID("00000000-0000-0000-0000-000000000001")
_GROUPED_LIGHT_ID = UUID("00000000-0000-0000-0000-000000000002")


class RecordingRooms:
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
        self.changes: list[tuple[float, int | None]] = []

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
    ) -> None:
        assert room_id == _ROOM_ID
        assert on is True
        self.changes.append((brightness, mirek))


class RecordingHue:
    def __init__(self) -> None:
        self.rooms = RecordingRooms()
        self.stream_started = False
        self.closed = False

    def on(self, event_type: type[object], handler: object) -> None:
        pass

    def off(self, event_type: type[object], handler: object) -> None:
        pass

    async def start_stream(self) -> None:
        self.stream_started = True

    async def close(self) -> None:
        self.closed = True


async def _dispatch_and_drain(event_bus: EventBus, listener: HueListener, event: Event) -> None:
    await event_bus.dispatch(event)
    await asyncio.wait_for(listener._jobs.join(), timeout=1)


def test_hue_listener_reacts_to_channel_agnostic_turn_lifecycle() -> None:
    async def run() -> RecordingHue:
        event_bus = EventBus()
        hue = RecordingHue()
        listener = HueListener(event_bus, room_name="Test room", hue=hue)
        try:
            await _dispatch_and_drain(event_bus, listener, SessionStarted())
            assert hue.rooms.changes == []

            await _dispatch_and_drain(event_bus, listener, UserTurnStarted())
            await _dispatch_and_drain(event_bus, listener, AssistantTurnStarted())
            await _dispatch_and_drain(event_bus, listener, ToolCallStarted(tool_name="weather"))
            await _dispatch_and_drain(event_bus, listener, ToolCallFinished(tool_name="weather"))
            await _dispatch_and_drain(event_bus, listener, ToolCallStarted(tool_name="calendar"))
            await _dispatch_and_drain(event_bus, listener, ToolCallStarted(tool_name="mail"))
            await _dispatch_and_drain(event_bus, listener, ToolCallFinished(tool_name="calendar"))
            await _dispatch_and_drain(event_bus, listener, ToolCallFinished(tool_name="mail"))
            await _dispatch_and_drain(event_bus, listener, SessionEnded())
            return hue
        finally:
            await listener.close()

    hue = asyncio.run(run())

    assert hue.stream_started is True
    assert hue.closed is True
    assert hue.rooms.changes == [
        (65.0, 223),
        (38.0, 368),
        (32.0, 389),
        (38.0, 368),
        (44.0, 389),
        (32.0, 389),
        (38.0, 368),
        (50.0, 292),
    ]


def test_hue_listener_folds_external_bridge_changes_into_the_baseline() -> None:
    async def run() -> list[tuple[float, int | None]]:
        event_bus = EventBus()
        hue = RecordingHue()
        listener = HueListener(event_bus, room_name="Test room", hue=hue)
        try:
            await _dispatch_and_drain(event_bus, listener, SessionStarted())
            await _dispatch_and_drain(event_bus, listener, UserTurnStarted())
            await listener._on_bridge_event(
                HueEvent.model_validate(
                    {
                        "id": _GROUPED_LIGHT_ID,
                        "type": "grouped_light",
                        "dimming": {"brightness": 75},
                        "color_temperature": {"mirek": 250},
                    }
                )
            )
            await _dispatch_and_drain(event_bus, listener, SessionEnded())
            return hue.rooms.changes
        finally:
            await listener.close()

    assert asyncio.run(run()) == [(65.0, 223), (60, 319)]
