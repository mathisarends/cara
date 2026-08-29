import pyrpckit as rpc

from gateway.presentation import Feature
from gateway.presentation.websocket.subscriptions import EVENT_STREAM_PROTOCOL

from . import automation, conversation, health

FEATURES: tuple[Feature, ...] = (
    health.feature,
    automation.feature,
    conversation.feature,
)


def gateway_protocol() -> rpc.RpcProtocol:
    return rpc.RpcProtocol(
        *(feature.protocol for feature in FEATURES if feature.protocol is not None),
        EVENT_STREAM_PROTOCOL,
    )


__all__ = ["FEATURES", "gateway_protocol"]
