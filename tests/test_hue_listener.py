import asyncio

from transitbus import Event, EventBus

from cara.events import (
    AssistantSpeechStarted,
    SessionEnded,
    SessionStarted,
    UserSpeechEnded,
    UserSpeechStarted,
)
from cara.listener import HueListener


class RecordingRoom:
    id = "room-id"
    is_on = True
    brightness_percentage = 50.0
    color_temperature_percentage = 40

    def __init__(self) -> None:
        self.changes: list[tuple[str, float]] = []

    async def set_brightness(self, brightness: float) -> None:
        self.changes.append(("brightness", brightness))

    async def set_color_temperature(self, temperature: float) -> None:
        self.changes.append(("temperature", temperature))


class RecordingRooms:
    def __init__(self, room: RecordingRoom) -> None:
        self._room = room

    def from_name(self, name: str) -> RecordingRoom:
        assert name == "Test room"
        return self._room


class RecordingHue:
    def __init__(self, room: RecordingRoom) -> None:
        self.rooms = RecordingRooms(room)
        self.connected = False

    def on(self, event_type: type[object], handler: object) -> None:
        pass

    async def connect(self) -> None:
        self.connected = True


async def _dispatch_and_drain(event_bus: EventBus, listener: HueListener, event: Event) -> None:
    await event_bus.dispatch(event)
    await asyncio.wait_for(listener._jobs.join(), timeout=1)


def test_hue_listener_reacts_only_to_speech_lifecycle() -> None:
    async def run() -> tuple[RecordingHue, RecordingRoom]:
        event_bus = EventBus()
        room = RecordingRoom()
        hue = RecordingHue(room)
        listener = HueListener(event_bus, room_name="Test room", hue=hue)
        try:
            await _dispatch_and_drain(event_bus, listener, SessionStarted())
            assert room.changes == []

            await _dispatch_and_drain(event_bus, listener, UserSpeechStarted())
            await _dispatch_and_drain(event_bus, listener, UserSpeechEnded())
            await _dispatch_and_drain(event_bus, listener, AssistantSpeechStarted())
            await _dispatch_and_drain(event_bus, listener, SessionEnded())
            return hue, room
        finally:
            if listener._worker is not None:
                listener._worker.cancel()
                await asyncio.gather(listener._worker, return_exceptions=True)

    hue, room = asyncio.run(run())

    assert hue.connected is True
    assert room.changes == [
        ("brightness", 65.0),
        ("temperature", 20),
        ("brightness", 50.0),
        ("temperature", 40),
        ("brightness", 70.0),
        ("temperature", 15),
        ("brightness", 50.0),
        ("temperature", 40),
    ]
