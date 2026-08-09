from typing import Any

import httpx

from gateway_client.errors import (
    GatewayConnectionError,
    GatewayNotFoundError,
    GatewayResponseError,
    GatewayValidationError,
)
from gateway_client.models import HTTPValidationError


class Transport:
    """HTTP transport shared by the generated operation namespaces."""

    def __init__(self, base_url: str, *, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    @property
    def base_url(self) -> str:
        return self._base_url

    async def request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise GatewayConnectionError(f"{method} {path} failed: {exc}") from exc
        if response.is_success:
            return response
        raise _response_error(response)

    async def aclose(self) -> None:
        await self._client.aclose()


def _response_error(response: httpx.Response) -> GatewayResponseError:
    if response.status_code == 422:
        validation = HTTPValidationError.model_validate_json(response.content)
        return GatewayValidationError(validation.detail)
    detail = _detail(response)
    if response.status_code == 404:
        return GatewayNotFoundError(detail)
    return GatewayResponseError(response.status_code, detail)


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text
    if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
        return payload["detail"]
    return response.text
