from gateway.features.conversation.application import ConversationEvent
from gateway.features.conversation.presentation.rpc.models import (
    SESSION_EVENT_ADAPTER,
    SessionEvent,
)


def session_event(event: ConversationEvent) -> SessionEvent:
    message = {
        "type": event.type,
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "session_id": event.session_id,
        "sequence": event.sequence,
        "metadata": event.metadata,
        **event.data,
    }
    if event.call_id is not None:
        message["call_id"] = event.call_id
    return SESSION_EVENT_ADAPTER.validate_python(message)
