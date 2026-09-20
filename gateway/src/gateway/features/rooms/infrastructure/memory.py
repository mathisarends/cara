from uuid import UUID

from gateway.features.rooms.application import RoomConnections, RoomStore
from gateway.features.rooms.domain import Room, RoomGroup


class InMemoryRoomStore(RoomStore):
    def __init__(self, rooms: tuple[Room, ...], groups: tuple[RoomGroup, ...]) -> None:
        self._rooms: dict[UUID, Room] = {room.room_id: room for room in rooms}
        self._groups: dict[UUID, RoomGroup] = {
            group.group_id: group for group in groups
        }

    def rooms(self) -> tuple[Room, ...]:
        return tuple(self._rooms.values())

    def groups(self) -> tuple[RoomGroup, ...]:
        return tuple(self._groups.values())

    def room(self, room_id: UUID) -> Room | None:
        return self._rooms.get(room_id)

    def group(self, group_id: UUID) -> RoomGroup | None:
        return self._groups.get(group_id)


class InMemoryRoomConnections(RoomConnections):
    def __init__(self) -> None:
        self._connections: dict[UUID, UUID] = {}

    def connect(self, room_id: UUID, connection_id: UUID) -> None:
        self._connections[room_id] = connection_id

    def disconnect(self, room_id: UUID, connection_id: UUID) -> None:
        if self._connections.get(room_id) == connection_id:
            self._connections.pop(room_id, None)

    def is_connected(self, room_id: UUID) -> bool:
        return room_id in self._connections
