from fastapi_canon import Feature

from .infrastructure import HealthProvider
from .presentation import health_router

feature = Feature(
    name="health",
    routers=[health_router],
    providers=[HealthProvider],
)

__all__ = ["feature"]
