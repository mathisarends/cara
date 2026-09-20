from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi_canon import CanonRouter

from room.features.health.application import ReadinessService
from room.features.health.presentation.errors import HEALTH_ERRORS, ROOM_NOT_READY
from room.features.health.presentation.schemas import (
    HealthResponse,
    ReadinessResponse,
)

health_router = CanonRouter(
    tags=["system"],
    route_class=DishkaRoute,
    error_registry=HEALTH_ERRORS,
)


@health_router.get(
    "/health",
    operation_id="get_room_health",
    response_model=HealthResponse,
    summary="Check room health",
)
async def health() -> HealthResponse:
    return HealthResponse()


@health_router.get(
    "/ready",
    operation_id="get_room_readiness",
    response_model=ReadinessResponse,
    summary="Check room readiness",
    raises=[ROOM_NOT_READY],
)
async def readiness(
    service: FromDishka[ReadinessService],
) -> ReadinessResponse:
    snapshot = service.require_ready()
    response = ReadinessResponse(
        ready=snapshot.ready,
        missing=snapshot.missing,
        gateway_connected=snapshot.gateway_connected,
    )
    return response
