from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi_canon import CanonRouter

from sandbox_manager.features.health.application import ReadinessService
from sandbox_manager.features.health.presentation.errors import (
    DEPENDENCY_UNAVAILABLE,
    HEALTH_ERRORS,
)
from sandbox_manager.features.health.presentation.schemas import (
    HealthResponse,
    ReadinessResponse,
)

health_router = CanonRouter(
    tags=["system"],
    route_class=DishkaRoute,
    error_registry=HEALTH_ERRORS,
)


@health_router.get(
    "/v1/health",
    operation_id="get_health",
    response_model=HealthResponse,
    response_description="The Sandbox Manager process is alive.",
    summary="Check Sandbox Manager health",
)
async def health() -> HealthResponse:
    return HealthResponse()


@health_router.get(
    "/v1/readiness",
    operation_id="get_readiness",
    response_model=ReadinessResponse,
    response_description="The Sandbox Manager can create sandboxes and serve files.",
    summary="Check Sandbox Manager readiness",
    raises=[DEPENDENCY_UNAVAILABLE],
)
async def readiness(service: FromDishka[ReadinessService]) -> ReadinessResponse:
    await service.check()
    return ReadinessResponse()
