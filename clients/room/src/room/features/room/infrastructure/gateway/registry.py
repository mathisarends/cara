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
    def __init__(self, url: str, *, token: str) -> None:
        self._http = httpx2.AsyncClient()
        self._client = GatewayRestClient(
            self._http,
            url,
            credentials={"GatewayToken": token},
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
        await self._client.register_room(room.room_id, request)

    async def close(self) -> None:
        await self._client.aclose()
        await self._http.aclose()
