from uuid import UUID

from gateway.features.rooms.application.ports import RoomConnections, RoomStore
from gateway.features.rooms.domain import (
    Device,
    DeviceStatus,
    Room,
    RoomGroup,
    RoomNotFoundError,
    RoomNotRegisteredError,
    RoomState,
)


class RoomRegistryService:
    def __init__(self, store: RoomStore, connections: RoomConnections) -> None:
        self._store = store
        self._connections = connections

    def list(self) -> tuple[Room, ...]:
        return self._store.rooms()

    def list_groups(self) -> tuple[RoomGroup, ...]:
        return self._store.groups()

    def get(self, room_id: UUID) -> Room:
        room = self._store.room(room_id)
        if room is None:
            raise RoomNotFoundError(f"Room {room_id!r} is not in the topology")
        return room

    def resolve(self, target: UUID) -> tuple[Room, ...]:
        room = self._store.room(target)
        if room is not None:
            return (room,)
        group = self._store.group(target)
        if group is None:
            raise RoomNotFoundError(f"Room or group {target!r} is not in the topology")
        return group.rooms

    def register(
        self, room_id: UUID, devices: tuple[Device, ...], client_version: str
    ) -> Room:
        room = self.get(room_id)
        room.register(devices, client_version)
        return room

    def require_registered(self, room_id: UUID) -> Room:
        room = self.get(room_id)
        if room.client_version is None:
            raise RoomNotRegisteredError(
                f"Room {room_id} must register before connecting"
            )
        return room

    def connect(self, room_id: UUID, connection_id: UUID) -> Room:
        room = self.require_registered(room_id)
        self._connections.connect(room_id, connection_id)
        room.connected()
        return room

    def disconnect(self, room_id: UUID, connection_id: UUID) -> None:
        room = self.get(room_id)
        self._connections.disconnect(room_id, connection_id)
        if not self._connections.is_connected(room_id):
            room.disconnected()

    def report_state(self, room_id: UUID, state: RoomState) -> None:
        self.get(room_id).report_state(state)

    def report_device(
        self, room_id: UUID, device_id: str, status: DeviceStatus
    ) -> None:
        self.get(room_id).report_device(device_id, status)

    def report_volume(self, room_id: UUID, volume: int) -> None:
        self.get(room_id).report_volume(volume)
