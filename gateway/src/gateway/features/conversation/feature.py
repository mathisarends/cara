from fastapi_canon import Feature

from gateway.features.conversation.infrastructure import ConversationProvider
from gateway.features.conversation.presentation import conversation_router

feature = Feature(
    name="conversation",
    routers=(conversation_router,),
    providers=(ConversationProvider,),
)
