from uuid import uuid4

from gateway.features.conversation.presentation.events import (
    SESSION_EVENT_ADAPTER,
    ChatDelta,
)


def test_event_union_is_flat_and_discriminated() -> None:
    event = SESSION_EVENT_ADAPTER.validate_python(
        {
            "type": "chat.delta",
            "event_id": str(uuid4()),
            "timestamp": "2026-08-20T12:00:00Z",
            "session_id": str(uuid4()),
            "sequence": 2,
            "text": "Hallo",
        }
    )

    assert isinstance(event, ChatDelta)
    assert event.text == "Hallo"
