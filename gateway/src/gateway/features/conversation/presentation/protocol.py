from gateway.features.conversation.presentation.events import SessionEvent
from gateway.features.conversation.presentation.rpc import RpcNotificationMethod
from gateway.features.conversation.presentation.rpc_methods import (
    ConversationRpcMethods,
)
from gateway.presentation.rpc import RpcNotificationDefinition, rpc_feature

CONVERSATION_PROTOCOL = rpc_feature(
    "conversation",
    handler=ConversationRpcMethods,
    notifications=(
        RpcNotificationDefinition(
            name=RpcNotificationMethod.SESSION_EVENT,
            payload=SessionEvent,
            summary="Publish a subscribed conversation session event.",
        ),
    ),
)
