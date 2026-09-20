from uuid import UUID

from pydantic import Field

from gateway.features.rooms.domain import (
    Capability,
    DeviceKind,
    DeviceStatus,
    RoomFunction,
    RoomState,
)
from gateway.presentation.models import ApiModel


class DeviceRegistration(ApiModel):
    device_id: str = Field(min_length=1)
    kind: DeviceKind
    capabilities: frozenset[Capability] = Field(min_length=1)


class RegisterRoomRequest(ApiModel):
    devices: tuple[DeviceRegistration, ...]
    client_version: str = Field(min_length=1)


class DeviceResponse(ApiModel):
    device_id: str
    kind: DeviceKind
    capabilities: frozenset[Capability]
    status: DeviceStatus


class RoomResponse(ApiModel):
    room_id: UUID
    display_name: str
    online: bool
    functions: frozenset[RoomFunction]
    state: RoomState
    volume: int | None
    client_version: str | None
    devices: tuple[DeviceResponse, ...]


class RoomListResponse(ApiModel):
    rooms: tuple[RoomResponse, ...]
