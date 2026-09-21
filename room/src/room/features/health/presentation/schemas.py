from pydantic import BaseModel, ConfigDict


class _ResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class HealthResponse(_ResponseModel):
    status: str = "ok"


class ReadinessResponse(_ResponseModel):
    ready: bool
    missing: tuple[str, ...]
    gateway_connected: bool
    voice_ready: bool
