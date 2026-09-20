from uuid import uuid4

from gateway.features.rooms.application import RoomRegistryService
from gateway.features.rooms.domain import Room
from gateway.features.rooms.infrastructure.memory import (
    InMemoryRoomConnections,
    InMemoryRoomStore,
)


def test_stale_disconnect_does_not_mark_reconnected_room_offline() -> None:
    room = Room(uuid4(), "Schlafzimmer")
    room.register((), "1.0.0")
    connections = InMemoryRoomConnections()
    store = InMemoryRoomStore((room,), ())
    registry = RoomRegistryService(store, connections)
    first_connection = uuid4()
    current_connection = uuid4()

    registry.connect(room.room_id, first_connection)
    registry.connect(room.room_id, current_connection)
    registry.disconnect(room.room_id, first_connection)

    assert room.online is True

    registry.disconnect(room.room_id, current_connection)

    assert room.online is False
