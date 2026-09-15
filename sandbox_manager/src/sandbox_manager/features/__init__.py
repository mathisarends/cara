from fastapi_canon import Feature

from . import files, health, sandbox

FEATURES: tuple[Feature, ...] = (
    health.feature,
    sandbox.feature,
    files.feature,
)

__all__ = ["FEATURES"]
