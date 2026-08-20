from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_protocol.events import SESSION_EVENT_ADAPTER, ChatDelta
from agent_protocol.rpc import (
    CONVERSATION_REQUEST_ADAPTER,
    RpcMethod,
    StartTurnRequest,
)


def test_request_union_is_discriminated_by_method() -> None:
    session_id = uuid4()

    request = CONVERSATION_REQUEST_ADAPTER.validate_python(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "turn.start",
            "params": {"session_id": str(session_id), "message": "hello"},
        }
    )

    assert isinstance(request, StartTurnRequest)
    assert request.method is RpcMethod.TURN_START
    assert request.params.session_id == session_id
    assert request.expects_response


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        CONVERSATION_REQUEST_ADAPTER.validate_python(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "session.create",
                "surprise": True,
            }
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
