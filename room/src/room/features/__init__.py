from fastapi_canon import Feature

from . import health, room

FEATURES: tuple[Feature, ...] = (
    health.feature,
    room.feature,
)

__all__ = ["FEATURES"]
