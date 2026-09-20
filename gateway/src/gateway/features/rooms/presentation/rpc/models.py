from pydantic import Field

from gateway.features.rooms.domain import DeviceStatus, RoomState
from gateway.presentation.models import ApiModel


class RoomStateReport(ApiModel):
    state: RoomState


class DeviceStatusReport(ApiModel):
    device_id: str = Field(min_length=1)
    status: DeviceStatus


class VolumeReport(ApiModel):
    volume: int = Field(ge=0, le=100)


class ReportAccepted(ApiModel):
    accepted: bool = True
