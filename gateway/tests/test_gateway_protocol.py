import json
from dataclasses import replace

import pytest

from gateway.features.conversation.presentation.events import ChatDelta
from gateway.features.conversation.presentation.protocol import (
    CONVERSATION_PROTOCOL,
)
from gateway.features.conversation.presentation.rpc import CreateSessionParams
from gateway.features.conversation.presentation.schemas import SessionResponse
from gateway.presentation import rpc
from gateway.presentation.protocol import GatewayProtocol, rpc_feature
from gateway.presentation.schema_export import (
    render_gateway_schema,
    render_openrpc_schema,
    write_gateway_schemas,
)


def test_protocol_derives_methods_from_decorated_handler_annotations() -> None:
    protocol = GatewayProtocol((CONVERSATION_PROTOCOL,))

    method = protocol.method("session.create")

    assert method.handler_name == "create_session"
    assert method.request_name == "CreateSessionRequest"
    assert method.params is CreateSessionParams
    assert method.result is SessionResponse


def test_protocol_derives_events_from_decorated_message_union() -> None:
    protocol = GatewayProtocol((CONVERSATION_PROTOCOL,))

    event = next(event for event in protocol.events if event.name == "chat.delta")

    assert event.payload is ChatDelta


def test_protocol_rejects_duplicate_method_names() -> None:
    method = CONVERSATION_PROTOCOL.methods[0]
    duplicate = replace(
        CONVERSATION_PROTOCOL,
        name="duplicate",
        methods=(method,),
        notifications=(),
        events=(),
    )

    with pytest.raises(ValueError, match="Duplicate RPC method: session.create"):
        GatewayProtocol((CONVERSATION_PROTOCOL, duplicate))


def test_feature_rejects_handler_without_typed_params() -> None:
    class InvalidRpcMethods:
        @rpc.method("invalid", summary="Invalid handler for testing.")
        async def invalid(self, params) -> SessionResponse:
            raise AssertionError

    with pytest.raises(TypeError, match="params must be a Pydantic model"):
        rpc_feature("invalid", handler=InvalidRpcMethods)


def test_generated_openrpc_keeps_method_result_and_event_payload_links() -> None:
    protocol = GatewayProtocol((CONVERSATION_PROTOCOL,))

    document = render_openrpc_schema(protocol)
    methods = {method["name"]: method for method in document["methods"]}
    events = {event["name"]: event for event in document["x-cara-events"]}

    assert methods["session.get"]["result"]["schema"] == {
        "$ref": "#/components/schemas/SessionSnapshotResponse"
    }
    assert methods["turn.start"]["x-cara-params-schema"] == {
        "$ref": "#/components/schemas/StartTurnParams"
    }
    assert events["chat.delta"]["payload"] == {"$ref": "#/components/schemas/ChatDelta"}
    event_schema = document["components"]["schemas"]["SessionEvent"]
    assert event_schema["discriminator"]["propertyName"] == "type"
    assert "chat.delta" in event_schema["discriminator"]["mapping"]


def test_schema_writer_creates_reproducible_documents(tmp_path) -> None:
    protocol = GatewayProtocol((CONVERSATION_PROTOCOL,))

    gateway_path, openrpc_path = write_gateway_schemas(tmp_path, protocol)

    assert json.loads(gateway_path.read_text(encoding="utf-8")) == (
        render_gateway_schema(protocol)
    )
    assert json.loads(openrpc_path.read_text(encoding="utf-8")) == (
        render_openrpc_schema(protocol)
    )
