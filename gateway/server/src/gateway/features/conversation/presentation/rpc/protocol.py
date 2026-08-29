from pyrpckit import RpcNotificationDefinition, feature

from gateway.features.conversation.presentation.rpc.handler import (
    ConversationRpcMethods,
)
from gateway.features.conversation.presentation.rpc.schemas import (
    RpcNotificationMethod,
    SessionEvent,
)

CONVERSATION_PROTOCOL = feature(
    "conversation",
    handlers=(ConversationRpcMethods,),
    notifications=(
        RpcNotificationDefinition(
            name=RpcNotificationMethod.SESSION_EVENT,
            payload=SessionEvent,
        ),
    ),
)
