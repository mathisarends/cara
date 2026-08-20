from gateway.presentation import Feature

from .infrastructure import ConversationProvider
from .presentation import (
    ConversationSocketProvider,
    event_router,
)

feature = Feature(
    name="conversation",
    routers=[event_router],
    providers=[ConversationProvider, ConversationSocketProvider],
)

__all__ = ["feature"]
