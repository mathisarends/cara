from fastapi_canon import Feature

from . import health, room, voice

FEATURES: tuple[Feature, ...] = (
    health.feature,
    room.feature,
    voice.feature,
)

__all__ = ["FEATURES"]
