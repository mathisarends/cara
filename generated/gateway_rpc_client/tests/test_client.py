from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest

from gateway_rpc_client import GatewayRpcClient


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False
        self.notification_values: list[dict[str, Any]] = []

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        self.calls.append((method, params))
        if method == "subscription.subscribe":
            return {"subscribed": params["sessionId"]}
        return {"sessionId": params["sessionId"]}

    async def notifications(self) -> AsyncIterator[dict[str, Any]]:
        for notification in self.notification_values:
            yield notification

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_namespaced_method_returns_typed_model() -> None:
    transport = FakeTransport()
    client = GatewayRpcClient(transport)
    session_id = uuid4()

    result = await client.subscription.subscribe(session_id=session_id)

    assert result.subscribed == session_id
    assert transport.calls == [
        ("subscription.subscribe", {"sessionId": str(session_id)})
    ]


@pytest.mark.asyncio
async def test_optional_parameters_are_omitted() -> None:
    transport = FakeTransport()
    client = GatewayRpcClient(transport)
    session_id = uuid4()

    await client.turn.start(session_id=session_id, message="Hallo")

    assert transport.calls == [
        ("turn.start", {"sessionId": str(session_id), "message": "Hallo"})
    ]


@pytest.mark.asyncio
async def test_params_model_serializes_uuid_for_transport() -> None:
    transport = FakeTransport()
    client = GatewayRpcClient(transport)
    session_id = uuid4()

    result = await client.turn.cancel(session_id=session_id)

    assert result.session_id == session_id
    assert transport.calls == [("turn.cancel", {"sessionId": str(session_id)})]


@pytest.mark.asyncio
async def test_turn_preparation_and_finish_use_session_commands() -> None:
    transport = FakeTransport()
    client = GatewayRpcClient(transport)
    session_id = uuid4()

    await client.turn.prepare(session_id=session_id)
    await client.turn.finish(session_id=session_id)

    assert transport.calls == [
        ("turn.prepare", {"sessionId": str(session_id)}),
        ("turn.finish", {"sessionId": str(session_id)}),
    ]


@pytest.mark.asyncio
async def test_notification_is_parsed_as_concrete_event() -> None:
    transport = FakeTransport()
    session_id = uuid4()
    transport.notification_values.append(
        {
            "jsonrpc": "2.0",
            "method": "session.event",
            "params": {
                "event_id": str(uuid4()),
                "timestamp": "2026-08-20T12:00:00Z",
                "session_id": str(session_id),
                "sequence": 3,
                "type": "chat.delta",
                "text": "Hallo",
            },
        }
    )
    client = GatewayRpcClient(transport)

    notifications = [item async for item in client.session.event()]

    assert notifications[0].type == "chat.delta"
    assert notifications[0].text == "Hallo"
