from fastapi_canon import Feature

from gateway.features.conversation.infrastructure import ConversationProvider
from gateway.features.conversation.presentation.rpc.methods import conversation_module

feature = Feature(
    name="conversation",
    providers=(ConversationProvider,),
)
rpc_module = conversation_module
