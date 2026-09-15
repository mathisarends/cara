import json

from gateway.app import create_app
from gateway.presentation.rpc.contract import gateway_contract
from gateway.presentation.schema_export import (
    render_openrpc_schema,
    write_gateway_schemas,
)


def test_generated_openrpc_keeps_method_result_and_event_payload_links() -> None:
    document = render_openrpc_schema(gateway_contract())
    methods = {method["name"]: method for method in document["methods"]}
    events = {event["name"]: event for event in document["x-rpc-notification-types"]}

    assert methods["turn.start"]["x-rpc-params-schema"] == {
        "$ref": "#/components/schemas/StartTurnParams"
    }
    assert events["chat.delta"]["payload"] == {"$ref": "#/components/schemas/ChatDelta"}
    event_schema = document["components"]["schemas"]["SessionEvent"]
    assert event_schema["discriminator"]["propertyName"] == "type"
    assert "chat.delta" in event_schema["discriminator"]["mapping"]


def test_openrpc_only_carries_connection_bound_methods() -> None:
    document = render_openrpc_schema(gateway_contract())

    assert {method["name"].split(".")[0] for method in document["methods"]} == {
        "subscription",
        "turn",
    }


def test_openapi_protects_resources_with_the_gateway_token() -> None:
    document = create_app().openapi()

    assert document["components"]["securitySchemes"]["GatewayToken"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert document["paths"]["/v1/sessions"]["post"]["security"] == [
        {"GatewayToken": []}
    ]
    assert "security" not in document["paths"]["/v1/health"]["get"]


def test_schema_writer_creates_reproducible_documents(tmp_path) -> None:
    contract = gateway_contract()
    openapi_path, openrpc_path = write_gateway_schemas(tmp_path, contract)

    assert json.loads(openapi_path.read_text(encoding="utf-8")) == (
        create_app().openapi()
    )
    assert json.loads(openrpc_path.read_text(encoding="utf-8")) == (
        render_openrpc_schema(contract)
    )
