from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx

from gateway_client.errors import (
    GatewayConnectionError,
    GatewayResponseError,
    GatewayValidationError,
    SessionNotFoundError,
)
from gateway_client.events import GatewayEventStream
from gateway_client.models import (
    ChatRequest,
    HealthResponse,
    HTTPValidationError,
    ReadinessResponse,
    SessionCreateRequest,
    SessionResponse,
)

_API_PREFIX = "/v1"


class GatewayClient:
    """Async client for the Cara Gateway HTTP API and its event stream."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        *,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

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
        await self._http.aclose()

    async def health(self) -> HealthResponse:
        response = await self._request("GET", f"{_API_PREFIX}/health")
        return HealthResponse.model_validate_json(response.content)

    async def readiness(self) -> ReadinessResponse:
        response = await self._request("GET", f"{_API_PREFIX}/readiness")
        return ReadinessResponse.model_validate_json(response.content)

    async def create_session(
        self,
        metadata: dict[str, Any] | None = None,
    ) -> SessionResponse:
        body = SessionCreateRequest(metadata=metadata or {})
        response = await self._request(
            "POST",
            f"{_API_PREFIX}/sessions",
            json=body.model_dump(mode="json"),
        )
        return SessionResponse.model_validate_json(response.content)

    async def get_session(self, session_id: UUID) -> SessionResponse:
        response = await self._request(
            "GET",
            f"{_API_PREFIX}/sessions/{session_id}",
            session_id=session_id,
        )
        return SessionResponse.model_validate_json(response.content)

    async def start_chat(
        self,
        session_id: UUID,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        body = ChatRequest(text=text, metadata=metadata or {})
        await self._request(
            "POST",
            f"{_API_PREFIX}/sessions/{session_id}/chat",
            session_id=session_id,
            json=body.model_dump(mode="json"),
        )

    async def cancel_chat(self, session_id: UUID) -> None:
        await self._request(
            "DELETE",
            f"{_API_PREFIX}/sessions/{session_id}/chat",
            session_id=session_id,
        )

    async def event_schema(self) -> dict[str, Any]:
        response = await self._request("GET", f"{_API_PREFIX}/schemas/events")
        return response.json()

    def events(self, session_id: UUID) -> GatewayEventStream:
        return GatewayEventStream(_event_stream_url(self._base_url, session_id))

    def session(self, session_id: UUID) -> "GatewaySession":
        return GatewaySession(self, session_id)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        session_id: UUID | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._http.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise GatewayConnectionError(f"{method} {path} failed: {exc}") from exc
        if response.is_success:
            return response
        raise _response_error(response, session_id)


class GatewaySession:
    """A single session bound to the client that created it."""

    def __init__(self, client: GatewayClient, session_id: UUID) -> None:
        self._client = client
        self._id = session_id

    @property
    def id(self) -> UUID:
        return self._id

    async def get(self) -> SessionResponse:
        return await self._client.get_session(self._id)

    async def send(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        await self._client.start_chat(self._id, text, metadata)

    async def cancel(self) -> None:
        await self._client.cancel_chat(self._id)

    def events(self) -> GatewayEventStream:
        return self._client.events(self._id)


def _event_stream_url(base_url: str, session_id: UUID) -> str:
    parsed = urlsplit(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = f"{parsed.path}{_API_PREFIX}/sessions/{session_id}/events"
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


def _response_error(
    response: httpx.Response,
    session_id: UUID | None,
) -> GatewayResponseError:
    if response.status_code == 422:
        validation = HTTPValidationError.model_validate_json(response.content)
        return GatewayValidationError(validation.detail)
    detail = _detail(response)
    if response.status_code == 404 and session_id is not None:
        return SessionNotFoundError(session_id, detail)
    return GatewayResponseError(response.status_code, detail)


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text
    if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
        return payload["detail"]
    return response.text
