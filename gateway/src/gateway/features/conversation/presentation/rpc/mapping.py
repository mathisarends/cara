from gateway.features.conversation.application import ConversationEvent
from gateway.features.conversation.presentation.rpc.models import (
    SESSION_EVENT_ADAPTER,
    SessionEvent,
)


def session_event(event: ConversationEvent) -> SessionEvent:
    message = event.model_dump(exclude={"channel"})
    return SESSION_EVENT_ADAPTER.validate_python(message)
