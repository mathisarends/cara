from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from gateway.features.conversation.presentation.events import (
    SESSION_EVENT_ADAPTER,
    ChatDelta,
)
from gateway.features.conversation.presentation.protocol import (
    CONVERSATION_PROTOCOL,
)
from gateway.features.conversation.presentation.rpc import StartTurnParams
from gateway.presentation.protocol import RpcRequestEnvelope


def test_request_params_are_selected_by_decorated_method() -> None:
    session_id = uuid4()
    request = RpcRequestEnvelope.model_validate(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "turn.start",
            "params": {"session_id": str(session_id), "message": "hello"},
        }
    )
    definition = next(
        method
        for method in CONVERSATION_PROTOCOL.methods
        if method.name == request.method
    )

    params = TypeAdapter(definition.params).validate_python(request.params)

    assert definition.handler_name == "start_turn"
    assert isinstance(params, StartTurnParams)
    assert params.session_id == session_id
    assert request.expects_response


def test_unknown_request_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        RpcRequestEnvelope.model_validate(
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
