import asyncio

import httpx
import pytest

from cara.tools.handler import IpLocationClient, Location

_RESPONSE = {
    "success": True,
    "city": "Berlin",
    "latitude": 52.52,
    "longitude": 13.405,
    "timezone": {"id": "Europe/Berlin"},
}


def _client(handler) -> IpLocationClient:
    return IpLocationClient(transport=httpx.MockTransport(handler))


def test_current_returns_location_for_the_public_ip() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://ipwho.is/")
        assert request.url.params["lang"] == "de"
        return httpx.Response(200, json=_RESPONSE)

    location = asyncio.run(_client(handler).current())

    assert location == Location(
        name="Berlin",
        latitude=52.52,
        longitude=13.405,
        timezone="Europe/Berlin",
    )


def test_current_reports_an_api_level_error() -> None:
    client = _client(lambda request: httpx.Response(200, json={"success": False, "message": "Reserved range"}))

    with pytest.raises(RuntimeError, match="Reserved range"):
        asyncio.run(client.current())
