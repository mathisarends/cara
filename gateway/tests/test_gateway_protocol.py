import json

import pytest

from gateway.features.conversation.presentation.protocol import (
    CONVERSATION_PROTOCOL,
)
from gateway.features.conversation.presentation.rpc import (
    CreateSessionParams,
    CreateSessionRequest,
)
from gateway.features.conversation.presentation.schemas import SessionResponse
from gateway.presentation.protocol import (
    GatewayProtocol,
    RpcFeatureDefinition,
    RpcMethodDefinition,
)
from gateway.presentation.schema_export import (
    render_gateway_schema,
    render_openrpc_schema,
    write_gateway_schemas,
)


def test_protocol_maps_methods_to_params_and_results() -> None:
    protocol = GatewayProtocol((CONVERSATION_PROTOCOL,))

    method = protocol.method("session.create")

    assert method.request is CreateSessionRequest
    assert method.params is CreateSessionParams
    assert method.result is SessionResponse


def test_protocol_rejects_duplicate_method_names() -> None:
    method = CONVERSATION_PROTOCOL.methods[0]
    duplicate = RpcFeatureDefinition(name="duplicate", methods=(method,))

    with pytest.raises(ValueError, match="Duplicate RPC method: session.create"):
        GatewayProtocol((CONVERSATION_PROTOCOL, duplicate))


def test_protocol_rejects_request_method_drift() -> None:
    invalid = RpcMethodDefinition(
        name="session.wrong",
        request=CreateSessionRequest,
        params=CreateSessionParams,
        result=SessionResponse,
        summary="Invalid test method.",
    )

    with pytest.raises(ValueError, match="does not declare method"):
        GatewayProtocol((RpcFeatureDefinition(name="invalid", methods=(invalid,)),))


def test_generated_openrpc_keeps_method_result_and_event_payload_links() -> None:
    protocol = GatewayProtocol((CONVERSATION_PROTOCOL,))

    document = render_openrpc_schema(protocol)
    methods = {method["name"]: method for method in document["methods"]}
    notifications = {
        notification["name"]: notification
        for notification in document["x-cara-notifications"]
    }

    assert methods["session.get"]["result"]["schema"] == {
        "$ref": "#/components/schemas/SessionSnapshotResponse"
    }
    assert methods["turn.start"]["x-cara-params-schema"] == {
        "$ref": "#/components/schemas/StartTurnParams"
    }
    assert notifications["session.event"]["payload"] == {
        "$ref": "#/components/schemas/SessionEvent"
    }
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
