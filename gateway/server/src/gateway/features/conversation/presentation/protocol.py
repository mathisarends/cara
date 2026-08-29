from pyrpckit import RpcNotificationDefinition, feature

from gateway.features.conversation.presentation.events import SessionEvent
from gateway.features.conversation.presentation.rpc import RpcNotificationMethod
from gateway.features.conversation.presentation.session_rpc_methods import (
    SessionRpcMethods,
)
from gateway.features.conversation.presentation.subscription_rpc_methods import (
    SubscriptionRpcMethods,
)
from gateway.features.conversation.presentation.turn_rpc_methods import (
    TurnRpcMethods,
)

CONVERSATION_PROTOCOL = feature(
    "conversation",
    handlers=(SessionRpcMethods, SubscriptionRpcMethods, TurnRpcMethods),
    notifications=(
        RpcNotificationDefinition(
            name=RpcNotificationMethod.SESSION_EVENT,
            payload=SessionEvent,
            summary="Publish a subscribed conversation session event.",
        ),
    ),
)
