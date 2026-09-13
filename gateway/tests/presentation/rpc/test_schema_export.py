import json

from gateway.presentation.rpc.contract import gateway_contract
from gateway.presentation.rpc.schema_export import (
    render_openrpc_schema,
    write_gateway_schema,
)


def test_generated_openrpc_keeps_method_result_and_event_payload_links() -> None:
    document = render_openrpc_schema(gateway_contract())
    methods = {method["name"]: method for method in document["methods"]}
    events = {event["name"]: event for event in document["x-rpc-notification-types"]}

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
    contract = gateway_contract()
    openrpc_path = write_gateway_schema(tmp_path, contract)

    assert json.loads(openrpc_path.read_text(encoding="utf-8")) == (
        render_openrpc_schema(contract)
    )
