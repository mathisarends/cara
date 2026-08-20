from gateway.presentation import Feature

from .infrastructure import ConversationProvider
from .presentation import (
    ConversationSocketProvider,
    event_router,
    install_protocol_openapi,
    schema_router,
)


def _configure_presentation(app) -> None:
    install_protocol_openapi(app)


feature = Feature(
    name="conversation",
    routers=[event_router, schema_router],
    providers=[ConversationProvider, ConversationSocketProvider],
    register_exception_handlers=_configure_presentation,
)

__all__ = ["feature"]
