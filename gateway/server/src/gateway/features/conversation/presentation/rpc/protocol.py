import pyrpckit as rpc

from gateway.features.conversation.presentation.rpc.handler import (
    ConversationRpcMethods,
)
from gateway.features.conversation.presentation.rpc.schemas import (
    RpcNotificationMethod,
    SessionEvent,
)

CONVERSATION_PROTOCOL = rpc.feature(
    "conversation",
    handlers=(ConversationRpcMethods,),
    notifications=(
        rpc.RpcNotificationDefinition(
            name=RpcNotificationMethod.SESSION_EVENT,
            payload=SessionEvent,
        ),
    ),
)
