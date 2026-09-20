from fastapi_canon import Feature

from .infrastructure import HealthProvider
from .presentation import HEALTH_ERRORS, health_router

feature = Feature(
    name="health",
    routers=(health_router,),
    providers=(HealthProvider,),
    errors=HEALTH_ERRORS,
)

__all__ = ["feature"]
