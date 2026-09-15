import httpx
import pytest

from cara_tools.weather.location import IpLocationLookup
from cara_tools.weather.models import Location


async def test_current_location_validates_success_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "city": "Berlin",
                "latitude": 52.52,
                "longitude": 13.405,
                "timezone": {"id": "Europe/Berlin"},
            },
        )

    lookup = IpLocationLookup(transport=httpx.MockTransport(handler))

    assert await lookup.current() == Location(
        name="Berlin",
        latitude=52.52,
        longitude=13.405,
        timezone="Europe/Berlin",
    )


async def test_current_location_reports_provider_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "message": "Reserved range"},
        )

    lookup = IpLocationLookup(transport=httpx.MockTransport(handler))

    with pytest.raises(RuntimeError, match="Reserved range"):
        await lookup.current()
