from gateway.presentation import Feature
from gateway.presentation.rpc.protocol import GatewayProtocol

from . import automation, conversation, health

FEATURES: tuple[Feature, ...] = (
    health.feature,
    automation.feature,
    conversation.feature,
)


def gateway_protocol() -> GatewayProtocol:
    return GatewayProtocol(
        feature.protocol for feature in FEATURES if feature.protocol is not None
    )


__all__ = ["FEATURES", "gateway_protocol"]
