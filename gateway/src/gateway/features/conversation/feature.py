from fastapi_canon import Feature

from gateway.features.conversation.infrastructure import ConversationProvider
from gateway.features.conversation.presentation import (
    conversation_router,
    turn_channel,
)

feature = Feature(
    name="conversation",
    routers=(conversation_router,),
    providers=(ConversationProvider,),
)
rpc_channels = (turn_channel,)
