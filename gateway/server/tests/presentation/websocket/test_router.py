import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

_AUTH_HEADERS = {
    "Authorization": "Bearer test-gateway-token-with-32-characters",
}


def test_gateway_socket_rejects_missing_credentials(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as error,
        client.websocket_connect("/v1/gateway"),
    ):
        pass

    assert error.value.code == 1008
    assert error.value.reason == "Unauthorized"


def test_gateway_socket_rejects_invalid_credentials(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as error,
        client.websocket_connect(
            "/v1/gateway",
            headers={"Authorization": "Bearer invalid-gateway-token"},
        ),
    ):
        pass

    assert error.value.code == 1008
    assert error.value.reason == "Unauthorized"


def test_automation_list_runs_over_gateway_socket(client: TestClient) -> None:
    with client.websocket_connect("/v1/gateway", headers=_AUTH_HEADERS) as socket:
        socket.send_json(
            {
                "jsonrpc": "2.0",
                "id": "automations",
                "method": "automation.list",
                "params": {"session_id": "090b4d71-8e4d-4b90-8981-8f38df122011"},
            }
        )
        response = socket.receive_json()

    assert response == {
        "jsonrpc": "2.0",
        "id": "automations",
        "result": {"automations": []},
    }


def test_unknown_automation_yields_resource_not_found(client: TestClient) -> None:
    with client.websocket_connect("/v1/gateway", headers=_AUTH_HEADERS) as socket:
        socket.send_json(
            {
                "jsonrpc": "2.0",
                "id": "automation",
                "method": "automation.get",
                "params": {
                    "session_id": "090b4d71-8e4d-4b90-8981-8f38df122011",
                    "automation_id": "missing",
                },
            }
        )
        response = socket.receive_json()

    assert response == {
        "jsonrpc": "2.0",
        "id": "automation",
        "error": {
            "code": -32004,
            "message": "Not found: Automation 'missing' not found",
        },
    }


def test_malformed_gateway_message_yields_json_rpc_parse_error(
    client: TestClient,
) -> None:
    with client.websocket_connect("/v1/gateway", headers=_AUTH_HEADERS) as socket:
        socket.send_text("not json")
        response = socket.receive_json()

    assert response == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32700, "message": "Parse error"},
    }


def test_conversation_request_runs_over_gateway_socket(client: TestClient) -> None:
    session_id = "090b4d71-8e4d-4b90-8981-8f38df122011"
    with client.websocket_connect("/v1/gateway", headers=_AUTH_HEADERS) as socket:
        socket.send_json(
            {
                "jsonrpc": "2.0",
                "id": "unsubscribe",
                "method": "subscription.unsubscribe",
                "params": {"session_id": session_id},
            }
        )
        response = socket.receive_json()

    assert response == {
        "jsonrpc": "2.0",
        "id": "unsubscribe",
        "result": {"unsubscribed": session_id},
    }
