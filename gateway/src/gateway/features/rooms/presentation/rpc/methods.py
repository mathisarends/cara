from fastapi_rpckit import Inject, RpcChannel

from gateway.features.rooms.application import RoomRegistryService
from gateway.features.rooms.presentation.rpc.models import (
    DeviceStatusReport,
    ReportAccepted,
    RoomStateReport,
    VolumeReport,
)
from gateway.rpc.sessions import RoomSocketSession

room_channel = RpcChannel("room")


@room_channel.method("report_state", idempotent=True)
async def report_state(
    params: RoomStateReport,
    room_session: Inject[RoomSocketSession],
    registry: Inject[RoomRegistryService],
) -> ReportAccepted:
    registry.report_state(room_session.room_id, params.state)
    return ReportAccepted()


@room_channel.method("report_device", idempotent=True)
async def report_device(
    params: DeviceStatusReport,
    room_session: Inject[RoomSocketSession],
    registry: Inject[RoomRegistryService],
) -> ReportAccepted:
    registry.report_device(room_session.room_id, params.device_id, params.status)
    return ReportAccepted()


@room_channel.method("report_volume", idempotent=True)
async def report_volume(
    params: VolumeReport,
    room_session: Inject[RoomSocketSession],
    registry: Inject[RoomRegistryService],
) -> ReportAccepted:
    registry.report_volume(room_session.room_id, params.volume)
    return ReportAccepted()
