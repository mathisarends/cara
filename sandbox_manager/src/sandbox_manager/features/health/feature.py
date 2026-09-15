from fastapi_canon import Feature

from sandbox_manager.features.health.infrastructure import HealthProvider
from sandbox_manager.features.health.presentation import health_router

feature = Feature(
    name="health",
    routers=[health_router],
    providers=[HealthProvider],
)
