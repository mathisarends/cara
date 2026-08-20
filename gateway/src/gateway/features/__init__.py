from gateway.presentation import Feature
from gateway.presentation.rpc.protocol import GatewayProtocol

from . import conversation, health

FEATURES: tuple[Feature, ...] = (health.feature, conversation.feature)


def gateway_protocol() -> GatewayProtocol:
    return GatewayProtocol(
        feature.protocol for feature in FEATURES if feature.protocol is not None
    )


__all__ = ["FEATURES", "gateway_protocol"]
