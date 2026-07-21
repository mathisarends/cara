from typing import Any

import httpx

from cara.tools.handler.weather import Location

_IP_LOCATION_URL = "https://ipwho.is/"


class IpLocationClient:
    """Determine the current approximate location from the public IP address."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 10.0) -> None:
        self._transport = transport
        self._timeout = timeout

    async def current(self) -> Location:
        data = await self._get()
        if data["success"] is not True:
            raise RuntimeError(f"IP location lookup failed: {data['message']}")

        return Location(
            name=data["city"],
            latitude=data["latitude"],
            longitude=data["longitude"],
            timezone=data["timezone"]["id"],
        )

    async def _get(self) -> dict[str, Any]:
        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
            response = await client.get(_IP_LOCATION_URL, params={"lang": "de"})
            response.raise_for_status()
            return response.json()
