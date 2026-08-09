from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter

from gateway.application import GatewayService
from gateway.presentation.protocol import HealthResponse, ReadinessResponse

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    operation_id="get_gateway_health",
    response_model=HealthResponse,
    response_description="The gateway process is alive.",
    summary="Check gateway health",
)
def health() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/readiness",
    operation_id="get_gateway_readiness",
    response_model=ReadinessResponse,
    response_description="The gateway application stack is ready.",
    summary="Check gateway readiness",
)
@inject
async def readiness(
    service: FromDishka[GatewayService],
) -> ReadinessResponse:
    del service
    return ReadinessResponse()
