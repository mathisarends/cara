from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi_canon import CanonRouter

from room.features.room.domain import Room
from room.features.room.presentation.schemas import (
    DeviceListResponse,
    DeviceResponse,
    RoomResponse,
)

room_router = CanonRouter(tags=["room"], route_class=DishkaRoute)


@room_router.get(
    "/room",
    operation_id="get_local_room",
    response_model=RoomResponse,
)
async def get_room(room: FromDishka[Room]) -> RoomResponse:
    response = RoomResponse(
        room_id=room.room_id,
        state=room.state,
        volume=room.volume,
    )
    return response


@room_router.get(
    "/devices",
    operation_id="list_local_devices",
    response_model=DeviceListResponse,
)
async def get_devices(room: FromDishka[Room]) -> DeviceListResponse:
    devices = tuple(
        DeviceResponse(
            device_id=device.device_id,
            kind=device.kind,
            capabilities=device.capabilities,
            status=device.status,
        )
        for device in room.devices
    )
    return DeviceListResponse(devices=devices)
