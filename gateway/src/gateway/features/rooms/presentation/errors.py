from fastapi_canon import Error, ErrorRegistry

from gateway.features.rooms.domain import RoomNotFoundError

ROOM_NOT_FOUND = Error(
    RoomNotFoundError,
    status=404,
    code="room_not_found",
    title="Room not found",
    detail=str,
)

ROOM_ERRORS = ErrorRegistry(name="rooms", errors=[ROOM_NOT_FOUND])
