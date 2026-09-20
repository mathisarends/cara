from uuid import UUID

from room.features.room.domain.device import Device
from room.features.room.domain.values import RoomState


class Room:
    def __init__(self, room_id: UUID, devices: tuple[Device, ...]) -> None:
        device_ids = [device.device_id for device in devices]
        if len(device_ids) != len(set(device_ids)):
            raise ValueError("Device IDs must be unique within a room")
        self._room_id = room_id
        self._devices = {device.device_id: device for device in devices}
        self._state = RoomState.IDLE
        self._volume: int | None = None

    @property
    def room_id(self) -> UUID:
        return self._room_id

    @property
    def devices(self) -> tuple[Device, ...]:
        return tuple(self._devices.values())

    @property
    def state(self) -> RoomState:
        return self._state

    @property
    def volume(self) -> int | None:
        return self._volume

    def change_state(self, state: RoomState) -> None:
        self._state = state

    def report_volume(self, volume: int) -> None:
        if not 0 <= volume <= 100:
            raise ValueError("volume must be between 0 and 100")
        self._volume = volume

    def device(self, device_id: str) -> Device:
        try:
            return self._devices[device_id]
        except KeyError as error:
            raise ValueError(f"Unknown device {device_id!r}") from error
