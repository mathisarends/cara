from collections.abc import AsyncIterator
from types import TracebackType
from typing import Self

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from gateway_client.errors import GatewayConnectionError
from gateway_client.models import GatewayEventMessage, event_adapter


class GatewayEventStream:
    """Async iterator over the WebSocket event feed of a single session.

    Open the stream before starting a turn; events emitted while no client is
    connected are not replayed.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: ClientConnection | None = None

    async def __aenter__(self) -> Self:
        try:
            self._connection = await connect(self._url)
        except (OSError, WebSocketException) as exc:
            raise GatewayConnectionError(f"Cannot open {self._url}: {exc}") from exc
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._connection is None:
            return
        connection, self._connection = self._connection, None
        await connection.close()

    async def __aiter__(self) -> AsyncIterator[GatewayEventMessage]:
        if self._connection is None:
            raise GatewayConnectionError("Event stream is not open.")
        try:
            async for message in self._connection:
                yield event_adapter.validate_json(message)
        except ConnectionClosed as exc:
            raise GatewayConnectionError("Event stream closed unexpectedly.") from exc
