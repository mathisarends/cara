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
        gateway_client: GatewayRpcClient,
        *,
        heartbeat_seconds: float,
    ) -> None:
        self._gateway_client = gateway_client
        self._heartbeat_seconds = heartbeat_seconds
        self._state = RoomState.IDLE
        self._closed = False

    async def report_state(self, state: RoomState) -> None:
        self._state = state
        await self._gateway_client.room.report_state(state=RpcRoomState(state.value))

    async def report_device(self, device_id: str, status: DeviceStatus) -> None:
        await self._gateway_client.room.report_device(
            device_id=device_id,
            status=RpcDeviceStatus(status.value),
        )

    async def report_volume(self, volume: int) -> None:
        await self._gateway_client.room.report_volume(volume=volume)

    async def wait_closed(self) -> None:
        while not self._closed:
            closure_signal = asyncio.shield(self._gateway_client.closed)
            try:
                # Shield the SDK's shared closure signal from heartbeat timeouts
                # and from cancellation when GatewayLink stops this waiter.
                error = await asyncio.wait_for(
                    closure_signal,
                    timeout=self._heartbeat_seconds,
                )
            except TimeoutError:
                await self.report_state(self._state)
            else:
                if error is not None:
                    raise error
                return

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._gateway_client.close()


class GatewayRoomConnector(RoomConnector):
    def __init__(
        self,
        gateway_url: str,
        room_id: UUID,
        *,
        gateway_token: str,
        heartbeat_seconds: float,
    ) -> None:
        self._gateway_url = gateway_url
        self._room_id = room_id
        self._gateway_token = gateway_token
        self._heartbeat_seconds = heartbeat_seconds

    async def connect(self) -> RoomConnection:
        gateway_client = await connect_room(
            self._gateway_url,
            self._room_id,
            token=self._gateway_token,
        )
        return GatewayRoomConnection(
            gateway_client,
            heartbeat_seconds=self._heartbeat_seconds,
        )
