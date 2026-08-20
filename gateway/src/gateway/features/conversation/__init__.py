from gateway.presentation import Feature

from .infrastructure import ConversationProvider

feature = Feature(
    name="conversation",
    providers=[ConversationProvider],
)

__all__ = ["feature"]
