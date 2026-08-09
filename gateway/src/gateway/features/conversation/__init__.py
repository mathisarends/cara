from gateway.presentation import Feature

from .infrastructure import ConversationProvider
from .presentation import (
    event_router,
    install_event_openapi,
    register_exception_handlers,
    schema_router,
    session_router,
)


def _configure_presentation(app) -> None:
    register_exception_handlers(app)
    install_event_openapi(app)


feature = Feature(
    name="conversation",
    routers=[session_router, event_router, schema_router],
    providers=[ConversationProvider],
    register_exception_handlers=_configure_presentation,
)

__all__ = ["feature"]
