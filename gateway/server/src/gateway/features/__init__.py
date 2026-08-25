from pyrpckit import RpcProtocol

from gateway.presentation import Feature

from . import automation, conversation, health

FEATURES: tuple[Feature, ...] = (
    health.feature,
    automation.feature,
    conversation.feature,
)


def gateway_protocol() -> RpcProtocol:
    return RpcProtocol(
        *(feature.protocol for feature in FEATURES if feature.protocol is not None)
    )


__all__ = ["FEATURES", "gateway_protocol"]
