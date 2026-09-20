from uuid import UUID

from gateway.features.rooms.domain.device import Device
from gateway.features.rooms.domain.values import (
    Capability,
    DeviceStatus,
    RoomFunction,
    RoomState,
)
from gateway.shared import Aggregate


class Room(Aggregate):
    def __init__(
        self,
        room_id: UUID,
        display_name: str,
    ) -> None:
        super().__init__(id=room_id)
        self._display_name = display_name
        self._devices: dict[str, Device] = {}
        self._online = False
        self._state = RoomState.IDLE
        self._volume: int | None = None
        self._client_version: str | None = None

    @property
    def room_id(self) -> UUID:
        return self.id

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def devices(self) -> tuple[Device, ...]:
        return tuple(self._devices.values())

    @property
    def online(self) -> bool:
        return self._online

    @property
    def state(self) -> RoomState:
        return self._state

    @property
    def volume(self) -> int | None:
        return self._volume

    @property
    def client_version(self) -> str | None:
        return self._client_version

    @property
    def functions(self) -> frozenset[RoomFunction]:
        if not self._online:
            return frozenset()
        capabilities = {
            capability
            for device in self._devices.values()
            if device.status is DeviceStatus.AVAILABLE
            for capability in device.capabilities
        }
        functions: set[RoomFunction] = set()
        if {Capability.AUDIO_INPUT, Capability.AUDIO_OUTPUT} <= capabilities:
            functions.add(RoomFunction.CONVERSATION)
        if Capability.AUDIO_OUTPUT in capabilities:
            functions.add(RoomFunction.ANNOUNCE)
        if Capability.MEDIA_PLAYBACK in capabilities:
            functions.add(RoomFunction.MUSIC)
        if Capability.LIGHT in capabilities:
            functions.add(RoomFunction.LIGHT)
        return frozenset(functions)

    def register(self, devices: tuple[Device, ...], client_version: str) -> None:
        self._devices = {device.device_id: device for device in devices}
        self._client_version = client_version

    def connected(self) -> None:
        self._online = True

    def disconnected(self) -> None:
        self._online = False
        self._state = RoomState.IDLE
        self._volume = None

    def report_state(self, state: RoomState) -> None:
        self._state = state

    def report_volume(self, volume: int) -> None:
        if not 0 <= volume <= 100:
            raise ValueError("Volume must be between 0 and 100")
        self._volume = volume

    def report_device(self, device_id: str, status: DeviceStatus) -> None:
        try:
            self._devices[device_id].report_status(status)
        except KeyError as error:
            raise ValueError(
                f"Unknown device {device_id!r} in room {self.room_id!r}"
            ) from error
