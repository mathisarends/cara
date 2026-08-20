from fastapi.testclient import TestClient

from gateway.main import create_app


def test_malformed_websocket_message_yields_json_rpc_parse_error() -> None:
    with (
        TestClient(create_app()) as client,
        client.websocket_connect("/v1/conversation") as socket,
    ):
        socket.send_text("not json")
        response = socket.receive_json()

    assert response == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32700, "message": "Parse error"},
    }


def test_protocol_schema_is_served_as_json_schema() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/conversation/schema")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/schema+json")
    assert "client_message" in response.json()["properties"]
