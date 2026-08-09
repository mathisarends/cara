from types import TracebackType
from typing import Self
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from gateway_client.events import GatewayEventStream
from gateway_client.operations import GatewayApi
from gateway_client.transport import Transport

_EVENT_STREAM_PATH = "/v1/sessions/{session_id}/events"


class GatewayClient(GatewayApi):
    """Entry point for the generated operation namespaces and the event stream.

    The WebSocket route is absent from the OpenAPI spec, so it is wired here
    rather than generated.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        *,
        timeout: float = 30.0,
    ) -> None:
        self._transport = Transport(base_url, timeout=timeout)
        super().__init__(self._transport)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._transport.aclose()

    def event_stream(self, session_id: UUID) -> GatewayEventStream:
        return GatewayEventStream(
            _event_stream_url(self._transport.base_url, session_id)
        )


def _event_stream_url(base_url: str, session_id: UUID) -> str:
    parsed = urlsplit(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path + _EVENT_STREAM_PATH.format(session_id=session_id)
    return urlunsplit((scheme, parsed.netloc, path, "", ""))
