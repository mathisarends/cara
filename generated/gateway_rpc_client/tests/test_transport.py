from collections.abc import AsyncIterator
from typing import Any

import pytest

from gateway_rpc_client import connect_gateway


class _Connection:
    def __aiter__(self) -> AsyncIterator[str]:
        return self._messages()

    async def close(self) -> None:
        pass

    async def _messages(self) -> AsyncIterator[str]:
        if False:
            yield ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "socket_url"),
    [
        ("http://gateway.test", "ws://gateway.test/v1/gateway"),
        ("https://gateway.test/", "wss://gateway.test/v1/gateway"),
    ],
)
async def test_connect_opens_the_gateway_socket_with_the_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
    socket_url: str,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    connection = _Connection()

    async def connect(url: str, **kwargs: Any) -> _Connection:
        calls.append((url, kwargs))
        return connection

    monkeypatch.setattr("gateway_rpc_client.authenticated.connect", connect)

    client = await connect_gateway(base_url, token="secret-token")
    await client.close()

    assert calls == [
        (
            socket_url,
            {
                "subprotocols": None,
                "additional_headers": {"Authorization": "Bearer secret-token"},
            },
        )
    ]
