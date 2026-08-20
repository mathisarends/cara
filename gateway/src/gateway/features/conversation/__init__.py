from gateway.presentation import Feature

from .infrastructure import ConversationProvider
from .presentation.protocol import CONVERSATION_PROTOCOL

feature = Feature(
    name="conversation",
    providers=[ConversationProvider],
    protocol=CONVERSATION_PROTOCOL,
)

__all__ = ["feature"]
