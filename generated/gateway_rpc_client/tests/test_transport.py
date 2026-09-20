from typing import Any
from uuid import uuid4

import pytest

from gateway_rpc_client import connect_gateway, connect_room


class _Connection:
    async def close(self) -> None:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "gateway_url"),
    [
        ("http://gateway.test", "ws://gateway.test"),
        ("https://gateway.test/", "wss://gateway.test"),
    ],
)
async def test_connect_opens_the_gateway_socket_with_the_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
    gateway_url: str,
) -> None:
    calls: list[dict[str, Any]] = []
    connection = _Connection()

    async def connect(**kwargs: Any) -> _Connection:
        calls.append(kwargs)
        return connection

    monkeypatch.setattr(
        "gateway_rpc_client.authenticated.GatewayRpcClient.connect",
        staticmethod(connect),
    )

    client = await connect_gateway(base_url, token="secret-token")
    await client.close()

    assert calls == [
        {
            "gateway_url": gateway_url,
            "headers": {"Authorization": "Bearer secret-token"},
            "eager": False,
        }
    ]


@pytest.mark.asyncio
async def test_connect_room_sets_the_room_endpoint_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    connection = _Connection()
    room_id = uuid4()

    async def connect(**kwargs: Any) -> _Connection:
        calls.append(kwargs)
        return connection

    monkeypatch.setattr(
        "gateway_rpc_client.authenticated.GatewayRpcClient.connect",
        staticmethod(connect),
    )

    client = await connect_room("https://gateway.test/", room_id, token="secret-token")
    await client.close()

    assert calls == [
        {
            "gateway_url": "wss://gateway.test",
            "room_id": str(room_id),
            "headers": {"Authorization": "Bearer secret-token"},
            "eager": False,
        }
    ]
