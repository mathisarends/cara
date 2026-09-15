import httpx

from cara_tools.weather.models import (
    IP_LOCATION_RESPONSE_ADAPTER,
    IpLocationFailure,
    IpLocationResponse,
    Location,
)

_IP_LOCATION_URL = "https://ipwho.is/"


class IpLocationLookup:
    """Determine the current approximate location from the public IP address."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    async def current(self) -> Location:
        data = await self._get()
        if isinstance(data, IpLocationFailure):
            raise RuntimeError(f"IP location lookup failed: {data.message}")

        return Location(
            name=data.city,
            latitude=data.latitude,
            longitude=data.longitude,
            timezone=data.timezone.id,
        )

    async def _get(self) -> IpLocationResponse:
        async with httpx.AsyncClient(
            transport=self._transport, timeout=self._timeout
        ) as client:
            response = await client.get(_IP_LOCATION_URL, params={"lang": "de"})
            response.raise_for_status()
            return IP_LOCATION_RESPONSE_ADAPTER.validate_python(response.json())
