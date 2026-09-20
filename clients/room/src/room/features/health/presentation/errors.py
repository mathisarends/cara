from fastapi_canon import Error, ErrorRegistry

from room.features.health.domain import RoomNotReadyError

ROOM_NOT_READY = Error(
    RoomNotReadyError,
    status=503,
    code="room_not_ready",
    title="Room not ready",
    detail=str,
)

HEALTH_ERRORS = ErrorRegistry(name="health", errors=[ROOM_NOT_READY])
