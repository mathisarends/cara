from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import Depends
from fastapi_canon import CanonRouter

from gateway.features.rooms.application import RoomRegistryService
from gateway.features.rooms.domain import Device
from gateway.features.rooms.presentation.errors import ROOM_ERRORS, ROOM_NOT_FOUND
from gateway.features.rooms.presentation.mapper import to_room_response
from gateway.features.rooms.presentation.schemas import (
    RegisterRoomRequest,
    RoomListResponse,
    RoomResponse,
)
from gateway.presentation.authentication import require_token

room_router = CanonRouter(
    prefix="/rooms",
    tags=["rooms"],
    route_class=DishkaRoute,
    error_registry=ROOM_ERRORS,
    dependencies=[Depends(require_token)],
)


@room_router.get("", operation_id="list_rooms", response_model=RoomListResponse)
async def list_rooms(
    registry: FromDishka[RoomRegistryService],
) -> RoomListResponse:
    rooms = registry.list()
    responses = tuple(to_room_response(room) for room in rooms)
    return RoomListResponse(rooms=responses)


@room_router.get(
    "/{room_id}",
    operation_id="get_room",
    response_model=RoomResponse,
    raises=[ROOM_NOT_FOUND],
)
async def get_room(
    room_id: UUID,
    registry: FromDishka[RoomRegistryService],
) -> RoomResponse:
    room = registry.get(room_id)
    response = to_room_response(room)
    return response


@room_router.put(
    "/{room_id}/registration",
    operation_id="register_room",
    response_model=RoomResponse,
    raises=[ROOM_NOT_FOUND],
)
async def register_room(
    room_id: UUID,
    request: RegisterRoomRequest,
    registry: FromDishka[RoomRegistryService],
) -> RoomResponse:
    devices = tuple(
        Device(item.device_id, item.kind, item.capabilities) for item in request.devices
    )
    room = registry.register(room_id, devices, request.client_version)
    response = to_room_response(room)
    return response
