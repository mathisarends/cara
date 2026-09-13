from collections.abc import AsyncIterator
from typing import Any

import pytest

from gateway_client import connect_gateway


class _Connection:
    def __aiter__(self) -> AsyncIterator[str]:
        return self._messages()

    async def close(self) -> None:
        pass

    async def _messages(self) -> AsyncIterator[str]:
        if False:
            yield ""


@pytest.mark.asyncio
async def test_connect_sends_the_gateway_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    connection = _Connection()

    async def connect(url: str, **kwargs: Any) -> _Connection:
        calls.append((url, kwargs))
        return connection

    monkeypatch.setattr("gateway_client.authenticated.connect", connect)

    client = await connect_gateway(
        "ws://gateway.test/v1/gateway",
        token="secret-token",
    )
    await client.close()

    assert calls == [
        (
            "ws://gateway.test/v1/gateway",
            {
                "subprotocols": None,
                "additional_headers": {"Authorization": "Bearer secret-token"},
            },
        )
    ]
