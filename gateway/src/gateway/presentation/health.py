from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel


class _HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class _ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"


router = APIRouter(tags=["system"])


@router.get(
    "/health",
    operation_id="get_gateway_health",
    response_model=_HealthResponse,
    response_description="The gateway process is alive.",
    summary="Check gateway health",
)
def health() -> _HealthResponse:
    return _HealthResponse()


@router.get(
    "/readiness",
    operation_id="get_gateway_readiness",
    response_model=_ReadinessResponse,
    response_description="The gateway application stack is ready.",
    summary="Check gateway readiness",
)
async def readiness() -> _ReadinessResponse:
    return _ReadinessResponse()
