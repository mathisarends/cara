import asyncio
from uuid import UUID

from gateway_rpc_client import GatewayRpcClient, connect_room
from gateway_rpc_client.models import DeviceStatus as RpcDeviceStatus
from gateway_rpc_client.models import RoomState as RpcRoomState
from room.features.room.application import RoomConnection, RoomConnector
from room.features.room.domain import DeviceStatus, RoomState


class GatewayRoomConnection(RoomConnection):
    def __init__(
        self,
        client: GatewayRpcClient,
        *,
        heartbeat_seconds: float,
    ) -> None:
        self._client = client
        self._heartbeat_seconds = heartbeat_seconds
        self._state = RoomState.IDLE
        self._closed = False

    async def report_state(self, state: RoomState) -> None:
        self._state = state
        await self._client.room.report_state(state=RpcRoomState(state.value))

    async def report_device(self, device_id: str, status: DeviceStatus) -> None:
        await self._client.room.report_device(
            device_id=device_id,
            status=RpcDeviceStatus(status.value),
        )

    async def report_volume(self, volume: int) -> None:
        await self._client.room.report_volume(volume=volume)

    async def wait_closed(self) -> None:
        while not self._closed:
            await asyncio.sleep(self._heartbeat_seconds)
            await self.report_state(self._state)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._client.close()


class GatewayRoomConnector(RoomConnector):
    def __init__(
        self,
        url: str,
        room_id: UUID,
        *,
        token: str,
        heartbeat_seconds: float,
    ) -> None:
        self._url = url
        self._room_id = room_id
        self._token = token
        self._heartbeat_seconds = heartbeat_seconds

    async def connect(self) -> RoomConnection:
        client = await connect_room(
            self._url,
            self._room_id,
            token=self._token,
        )
        return GatewayRoomConnection(
            client,
            heartbeat_seconds=self._heartbeat_seconds,
        )
