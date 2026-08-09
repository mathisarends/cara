from gateway.presentation import Feature

from .infrastructure import ConversationProvider
from .presentation import (
    event_router,
    register_exception_handlers,
    session_router,
)

feature = Feature(
    name="conversation",
    routers=[session_router, event_router],
    providers=[ConversationProvider],
    register_exception_handlers=register_exception_handlers,
)

__all__ = ["feature"]
