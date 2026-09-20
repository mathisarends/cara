from uuid import UUID

from pydantic import BaseModel, ConfigDict

from room.features.room.domain import Capability, DeviceKind, DeviceStatus, RoomState


class _ResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class DeviceResponse(_ResponseModel):
    device_id: str
    kind: DeviceKind
    capabilities: frozenset[Capability]
    status: DeviceStatus


class RoomResponse(_ResponseModel):
    room_id: UUID
    state: RoomState
    volume: int | None


class DeviceListResponse(_ResponseModel):
    devices: tuple[DeviceResponse, ...]
