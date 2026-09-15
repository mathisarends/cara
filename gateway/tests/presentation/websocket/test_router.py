from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

_AUTH_HEADERS = {
    "Authorization": "Bearer test-gateway-token-with-32-characters",
}


def test_gateway_socket_rejects_missing_credentials(
    anonymous_client: TestClient,
) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as error,
        anonymous_client.websocket_connect("/v1/gateway"),
    ):
        pass

    assert error.value.code == 1008
    assert error.value.reason == "Unauthorized"


def test_gateway_socket_rejects_invalid_credentials(
    anonymous_client: TestClient,
) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as error,
        anonymous_client.websocket_connect(
            "/v1/gateway",
            headers={"Authorization": "Bearer invalid-gateway-token"},
        ),
    ):
        pass

    assert error.value.code == 1008
    assert error.value.reason == "Unauthorized"


def test_turn_command_for_an_unknown_session_yields_resource_not_found(
    client: TestClient,
) -> None:
    with client.websocket_connect("/v1/gateway", headers=_AUTH_HEADERS) as socket:
        socket.send_json(
            {
                "jsonrpc": "2.0",
                "id": "prepare",
                "method": "turn.prepare",
                "params": {"sessionId": str(uuid4())},
            }
        )
        response = socket.receive_json()

    assert response["id"] == "prepare"
    assert response["error"]["code"] == -32004


@pytest.mark.parametrize("method", ["session.open", "automation.list", "alarm.list"])
def test_resource_methods_are_served_over_rest_only(
    client: TestClient,
    method: str,
) -> None:
    with client.websocket_connect("/v1/gateway", headers=_AUTH_HEADERS) as socket:
        socket.send_json({"jsonrpc": "2.0", "id": "resource", "method": method})
        response = socket.receive_json()

    assert response["error"]["code"] == -32601


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
                "params": {"sessionId": session_id},
            }
        )
        response = socket.receive_json()

    assert response == {
        "jsonrpc": "2.0",
        "id": "unsubscribe",
        "result": {"unsubscribed": session_id},
    }


def test_channel_subscription_runs_over_gateway_socket(client: TestClient) -> None:
    with client.websocket_connect("/v1/gateway", headers=_AUTH_HEADERS) as socket:
        socket.send_json(
            {
                "jsonrpc": "2.0",
                "id": "subscribe-channel",
                "method": "subscription.subscribe_channel",
                "params": {"channel": "voice"},
            }
        )
        response = socket.receive_json()

    assert response == {
        "jsonrpc": "2.0",
        "id": "subscribe-channel",
        "result": {"subscribedChannel": "voice"},
    }
