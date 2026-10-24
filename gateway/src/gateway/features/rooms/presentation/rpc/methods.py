from fastapi_rpckit import Inject, RpcChannel

from gateway.features.rooms.application import RoomRegistryService
from gateway.features.rooms.presentation.rpc.errors import (
    ROOM_DEVICE_NOT_FOUND,
    ROOM_NOT_FOUND,
)
from gateway.features.rooms.presentation.rpc.models import (
    DeviceStatusReport,
    ReportAccepted,
    RoomStateReport,
    VolumeReport,
)
from gateway.rpc.context import RoomSocketSession

room_channel = RpcChannel("room", raises=(ROOM_NOT_FOUND,))


@room_channel.method("report_state", idempotent=True)
async def report_state(
    params: RoomStateReport,
    room_session: Inject[RoomSocketSession],
    room_registry_service: Inject[RoomRegistryService],
) -> ReportAccepted:
    room_registry_service.report_state(room_session.room_id, params.state)
    return ReportAccepted()


@room_channel.method("report_device", idempotent=True, raises=(ROOM_DEVICE_NOT_FOUND,))
async def report_device(
    params: DeviceStatusReport,
    room_session: Inject[RoomSocketSession],
    room_registry_service: Inject[RoomRegistryService],
) -> ReportAccepted:
    room_registry_service.report_device(
        room_session.room_id, params.device_id, params.status
    )
    return ReportAccepted()


@room_channel.method("report_volume", idempotent=True)
async def report_volume(
    params: VolumeReport,
    room_session: Inject[RoomSocketSession],
    room_registry_service: Inject[RoomRegistryService],
) -> ReportAccepted:
    room_registry_service.report_volume(room_session.room_id, params.volume)
    return ReportAccepted()
