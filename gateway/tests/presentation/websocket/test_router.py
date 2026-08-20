from fastapi.testclient import TestClient


def test_malformed_gateway_message_yields_json_rpc_parse_error(
    client: TestClient,
) -> None:
    with client.websocket_connect("/v1/gateway") as socket:
        socket.send_text("not json")
        response = socket.receive_json()

    assert response == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32700, "message": "Parse error"},
    }


def test_conversation_request_runs_over_gateway_socket(client: TestClient) -> None:
    session_id = "090b4d71-8e4d-4b90-8981-8f38df122011"
    with client.websocket_connect("/v1/gateway") as socket:
        socket.send_json(
            {
                "jsonrpc": "2.0",
                "id": "unsubscribe",
                "method": "session.unsubscribe",
                "params": {"session_id": session_id},
            }
        )
        response = socket.receive_json()

    assert response == {
        "jsonrpc": "2.0",
        "id": "unsubscribe",
        "result": {"unsubscribed": session_id},
    }
