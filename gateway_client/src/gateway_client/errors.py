from typing import Any


class GatewayClientError(Exception):
    """Base error raised by the generated gateway client."""


class GatewayRpcError(GatewayClientError):
    def __init__(
        self,
        code: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"Gateway RPC error {code}: {message}")
        self._code = code
        self._message = message
        self._data = data

    @property
    def code(self) -> int:
        return self._code

    @property
    def message(self) -> str:
        return self._message

    @property
    def data(self) -> dict[str, Any] | None:
        return self._data


class GatewayTransportError(GatewayClientError):
    """Raised when the WebSocket connection cannot serve an RPC request."""
