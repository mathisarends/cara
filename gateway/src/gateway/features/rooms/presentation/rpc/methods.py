from uuid import UUID

from pyrpckit import Inject, RpcChannel, RpcConnection

from gateway.features.rooms.application import RoomRegistryService
from gateway.features.rooms.presentation.rpc.models import (
    DeviceStatusReport,
    ReportAccepted,
    RoomStateReport,
    VolumeReport,
)

room_channel = RpcChannel("room")


@room_channel.server.method("report_state")
async def report_state(
    params: RoomStateReport,
    connection: Inject[RpcConnection],
    registry: Inject[RoomRegistryService],
) -> ReportAccepted:
    room_id = UUID(connection.path_params["room_id"])
    registry.report_state(room_id, params.state)
    return ReportAccepted()


@room_channel.server.method("report_device")
async def report_device(
    params: DeviceStatusReport,
    connection: Inject[RpcConnection],
    registry: Inject[RoomRegistryService],
) -> ReportAccepted:
    room_id = UUID(connection.path_params["room_id"])
    registry.report_device(room_id, params.device_id, params.status)
    return ReportAccepted()


@room_channel.server.method("report_volume")
async def report_volume(
    params: VolumeReport,
    connection: Inject[RpcConnection],
    registry: Inject[RoomRegistryService],
) -> ReportAccepted:
    room_id = UUID(connection.path_params["room_id"])
    registry.report_volume(room_id, params.volume)
    return ReportAccepted()
