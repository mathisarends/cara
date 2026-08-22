import json

from gateway.features.conversation.presentation.protocol import CONVERSATION_PROTOCOL
from gateway.presentation.rpc.schema_export import (
    render_gateway_schema,
    render_openrpc_schema,
    write_gateway_schemas,
)
from rpckit import RpcProtocol


def test_generated_openrpc_keeps_method_result_and_event_payload_links() -> None:
    protocol = RpcProtocol(CONVERSATION_PROTOCOL)

    document = render_openrpc_schema(protocol)
    methods = {method["name"]: method for method in document["methods"]}
    events = {event["name"]: event for event in document["x-rpc-events"]}

    assert methods["session.get"]["result"]["schema"] == {
        "$ref": "#/components/schemas/SessionSnapshotResponse"
    }
    assert methods["turn.start"]["x-rpc-params-schema"] == {
        "$ref": "#/components/schemas/StartTurnParams"
    }
    assert events["chat.delta"]["payload"] == {"$ref": "#/components/schemas/ChatDelta"}
    event_schema = document["components"]["schemas"]["SessionEvent"]
    assert event_schema["discriminator"]["propertyName"] == "type"
    assert "chat.delta" in event_schema["discriminator"]["mapping"]


def test_schema_writer_creates_reproducible_documents(tmp_path) -> None:
    protocol = RpcProtocol(CONVERSATION_PROTOCOL)

    gateway_path, openrpc_path = write_gateway_schemas(tmp_path, protocol)

    assert json.loads(gateway_path.read_text(encoding="utf-8")) == (
        render_gateway_schema(protocol)
    )
    assert json.loads(openrpc_path.read_text(encoding="utf-8")) == (
        render_openrpc_schema(protocol)
    )
