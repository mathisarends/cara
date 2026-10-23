from uuid import UUID

from fastapi_rpckit import Inject, RpcChannel, RpcConnection

from gateway.features.rooms.application import RoomRegistryService
from gateway.features.rooms.presentation.rpc.models import (
    DeviceStatusReport,
    ReportAccepted,
    RoomStateReport,
    VolumeReport,
)

room_channel = RpcChannel("room")


@room_channel.method("report_state", idempotent=True)
async def report_state(
    params: RoomStateReport,
    connection: Inject[RpcConnection],
    registry: Inject[RoomRegistryService],
) -> ReportAccepted:
    room_id = UUID(connection.path_params["room_id"])
    registry.report_state(room_id, params.state)
    return ReportAccepted()


@room_channel.method("report_device", idempotent=True)
async def report_device(
    params: DeviceStatusReport,
    connection: Inject[RpcConnection],
    registry: Inject[RoomRegistryService],
) -> ReportAccepted:
    room_id = UUID(connection.path_params["room_id"])
    registry.report_device(room_id, params.device_id, params.status)
    return ReportAccepted()


@room_channel.method("report_volume", idempotent=True)
async def report_volume(
    params: VolumeReport,
    connection: Inject[RpcConnection],
    registry: Inject[RoomRegistryService],
) -> ReportAccepted:
    room_id = UUID(connection.path_params["room_id"])
    registry.report_volume(room_id, params.volume)
    return ReportAccepted()
