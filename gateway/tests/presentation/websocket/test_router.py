import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi_rpckit.integrations.dishka import DishkaResolver
from fastapi_rpckit.testing import InMemorySocket, RpcTestClient, RpcTestError
from starlette.testclient import WebSocketDenialResponse

from gateway.features.conversation.application import (
    ConversationEventType,
    create_conversation_event,
)
from gateway.features.conversation.domain.values import ChannelRef
from gateway.features.voice.application import VoiceEvent, VoiceEventType
from gateway.presentation.error_mapping import gateway_error_mapper
from gateway.presentation.rpc.service import gateway_service
from gateway.presentation.subscriptions import InMemoryEventStream

_AUTH_HEADERS = {
    "Authorization": "Bearer test-gateway-token-with-32-characters",
}


def test_gateway_socket_rejects_missing_credentials(
    anonymous_client: TestClient,
) -> None:
    with (
        pytest.raises(WebSocketDenialResponse) as denial,
        anonymous_client.websocket_connect("/v1/gateway"),
    ):
        pass

    assert denial.value.status_code == 401
    assert denial.value.text == "Unauthorized"


def test_gateway_socket_rejects_invalid_credentials(
    anonymous_client: TestClient,
) -> None:
    with (
        pytest.raises(WebSocketDenialResponse) as denial,
        anonymous_client.websocket_connect(
            "/v1/gateway",
            headers={"Authorization": "Bearer invalid-gateway-token"},
        ),
    ):
        pass

    assert denial.value.status_code == 401
    assert denial.value.text == "Unauthorized"


def test_turn_command_for_an_unknown_session_yields_resource_not_found(
    client: TestClient,
) -> None:
    with pytest.raises(RpcTestError) as error:
        _request(client, "turn.prepare", {"sessionId": str(uuid4())})

    assert error.value.rpc_code == -32004
    assert error.value.code == "resource_not_found"


@pytest.mark.parametrize("method", ["session.open", "automation.list", "alarm.list"])
def test_resource_methods_are_served_over_rest_only(
    client: TestClient,
    method: str,
) -> None:
    with pytest.raises(RpcTestError) as error:
        _request(client, method)

    assert error.value.rpc_code == -32601


def test_malformed_gateway_message_yields_json_rpc_parse_error(
    client: TestClient,
) -> None:
    response = client.portal.call(_send_raw, client.app, "not json")

    assert response == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {
            "code": -32700,
            "message": "Parse error",
            "data": {"code": "parse_error", "details": None},
        },
    }


def test_conversation_request_runs_over_gateway_socket(client: TestClient) -> None:
    session_id = "090b4d71-8e4d-4b90-8981-8f38df122011"

    result = _request(client, "subscription.unsubscribe", {"sessionId": session_id})

    assert result == {"unsubscribed": session_id}


def test_channel_subscription_runs_over_gateway_socket(client: TestClient) -> None:
    result = _request(client, "subscription.subscribe_channel", {"channel": "voice"})

    assert result == {"subscribedChannel": "voice"}


def test_both_event_streams_reach_a_subscribed_client(client: TestClient) -> None:
    session_id = client.post("/v1/sessions", json={"channel": {"name": "cli"}}).json()[
        "id"
    ]

    methods = client.portal.call(_receive_published_events, client.app, session_id)

    assert sorted(methods) == ["session.event", "voice.event"]


# Exercise RPC dispatch with the library's in-memory client; handshake and
# connection cleanup also run through the ASGI routes in the integration tests.
def _request(
    client: TestClient,
    method: str,
    params: dict[str, Any] | None = None,
) -> Any:
    return client.portal.call(_serve_request, client.app, method, params)


async def _serve_request(
    app: FastAPI,
    method: str,
    params: dict[str, Any] | None,
) -> Any:
    async with _gateway(app) as gateway:
        return await gateway.request(method, params)


async def _receive_published_events(app: FastAPI, session_id: str) -> list[str]:
    stream = await app.state.dishka_container.get(InMemoryEventStream)
    async with _gateway(app) as gateway:
        await gateway.request("subscription.subscribe", {"sessionId": session_id})
        await stream.publish(
            VoiceEvent(
                VoiceEventType.TURN_COMPLETED,
                uuid4(),
                UUID(session_id),
                {},
                voice_turn_id=uuid4(),
                sequence=4,
            )
        )
        await stream.publish(
            create_conversation_event(
                ConversationEventType.CHAT_COMPLETED,
                UUID(session_id),
                ChannelRef(name="cli"),
                {"text": "done", "finish_reason": "stop"},
                sequence=1,
            )
        )
        return [(await gateway.next_notification())[0] for _ in range(2)]


async def _send_raw(app: FastAPI, frame: str) -> Any:
    socket = InMemorySocket("/v1/gateway", headers=_AUTH_HEADERS)
    resolver = DishkaResolver(app.state.dishka_container)
    serving = asyncio.create_task(gateway_service.serve(socket, resolver=resolver))
    try:
        await socket.client_send(frame)
        return json.loads(await socket.client_receive())
    finally:
        await socket.client_disconnect()
        await serving


def _gateway(app: FastAPI) -> RpcTestClient:
    resolver = DishkaResolver(app.state.dishka_container)
    return RpcTestClient(
        gateway_service,
        "/v1/gateway",
        headers=_AUTH_HEADERS,
        resolver=resolver,
        error_mapper=gateway_error_mapper,
    )
