from gateway.features.conversation.infrastructure import ConversationProvider
from gateway.features.conversation.presentation import CONVERSATION_PROTOCOL
from gateway.presentation import Feature

feature = Feature(
    name="conversation",
    providers=(ConversationProvider,),
    protocol=CONVERSATION_PROTOCOL,
)
