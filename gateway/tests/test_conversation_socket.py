from fastapi.testclient import TestClient

from gateway.app import create_app


def _create_test_app(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    return create_app()


def test_malformed_websocket_message_yields_json_rpc_parse_error(monkeypatch) -> None:
    with (
        TestClient(_create_test_app(monkeypatch)) as client,
        client.websocket_connect("/v1/conversation") as socket,
    ):
        socket.send_text("not json")
        response = socket.receive_json()

    assert response == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32700, "message": "Parse error"},
    }
