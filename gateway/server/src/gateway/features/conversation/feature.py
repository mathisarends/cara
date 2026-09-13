from gateway.features.conversation.infrastructure import ConversationProvider
from gateway.features.conversation.presentation.rpc.methods import conversation_module
from gateway.presentation import Feature

feature = Feature(
    name="conversation",
    providers=(ConversationProvider,),
    module=conversation_module,
)
