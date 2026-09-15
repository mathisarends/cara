import logging

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from gateway.features.health.application import ReadinessService
from gateway.features.health.presentation.schemas import (
    HealthResponse,
    ReadinessResponse,
)

logger = logging.getLogger(__name__)


health_router = APIRouter(tags=["system"], route_class=DishkaRoute)


@health_router.get(
    "/v1/health",
    operation_id="get_gateway_health",
    response_model=HealthResponse,
    response_description="The gateway process is alive.",
    summary="Check gateway health",
)
async def health() -> HealthResponse:
    return HealthResponse()


@health_router.get(
    "/v1/readiness",
    operation_id="get_gateway_readiness",
    response_model=ReadinessResponse,
    response_description="The gateway application stack is ready.",
    summary="Check gateway readiness",
)
async def readiness(
    service: FromDishka[ReadinessService],
) -> ReadinessResponse:
    try:
        await service.check()
    except SQLAlchemyError as error:
        logger.exception("Gateway readiness check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway dependencies are unavailable.",
        ) from error
    return ReadinessResponse()
