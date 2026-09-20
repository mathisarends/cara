from importlib.metadata import version

import httpx2

from gateway_rest_client import (
    Capability,
    DeviceKind,
    DeviceRegistration,
    GatewayRestClient,
    RegisterRoomRequest,
)
from room.features.room.application import GatewayRegistry
from room.features.room.domain import Room


class GatewayRoomRegistry(GatewayRegistry):
    def __init__(self, gateway_url: str, *, gateway_token: str) -> None:
        self._http_client = httpx2.AsyncClient()
        self._gateway_client = GatewayRestClient(
            self._http_client,
            gateway_url,
            credentials={"GatewayToken": gateway_token},
        )

    async def register(self, room: Room) -> None:
        devices = tuple(
            DeviceRegistration(
                device_id=device.device_id,
                kind=DeviceKind(device.kind.value),
                capabilities=frozenset(
                    Capability(capability.value) for capability in device.capabilities
                ),
            )
            for device in room.devices
        )
        request = RegisterRoomRequest(
            devices=devices,
            client_version=version("room-client"),
        )
        await self._gateway_client.register_room(room.room_id, request)

    async def close(self) -> None:
        await self._gateway_client.aclose()
        await self._http_client.aclose()
