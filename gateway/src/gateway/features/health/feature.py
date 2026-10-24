from fastapi_canon import Feature

from gateway.features.health.infrastructure import HealthProvider
from gateway.features.health.presentation import health_router

feature = Feature(name="health", routers=[health_router], providers=[HealthProvider])
