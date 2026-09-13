from gateway.presentation import Feature

from . import automation, conversation, health

FEATURES: tuple[Feature, ...] = (
    health.feature,
    automation.feature,
    conversation.feature,
)
__all__ = ["FEATURES"]
