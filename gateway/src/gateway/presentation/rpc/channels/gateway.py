from pyrpckit import RpcChannel

from gateway.features import FEATURES
from gateway.features.conversation.presentation.rpc.events import session_events_module
from gateway.features.conversation.presentation.rpc.subscriptions import (
    subscription_module,
)


def gateway_channel() -> RpcChannel:
    channel = RpcChannel(name="local")
    for feature in FEATURES:
        if feature.module is not None:
            channel.include(feature.module)
    channel.include(subscription_module)
    channel.include(session_events_module)
    return channel
