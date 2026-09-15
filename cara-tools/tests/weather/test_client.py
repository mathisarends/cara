import httpx
import pytest

from cara_tools.weather.client import OpenMeteoWeather
from cara_tools.weather.models import Location

_BERLIN = Location(
    name="Berlin",
    latitude=52.52,
    longitude=13.405,
    timezone="Europe/Berlin",
)

_FORECAST = {
    "current": {
        "time": "2026-07-21T14:00",
        "temperature_2m": 24.1,
        "apparent_temperature": 22.0,
        "weather_code": 2,
        "wind_speed_10m": 11.3,
        "is_day": 1,
    },
    "hourly": {
        "time": ["2026-07-21T13:00", "2026-07-21T14:00"],
        "temperature_2m": [23.5, 24.1],
        "weather_code": [2, 61],
        "precipitation_probability": [5, 60],
    },
    "daily": {
        "time": ["2026-07-21"],
        "weather_code": [2],
        "temperature_2m_max": [26.0],
        "temperature_2m_min": [15.0],
        "precipitation_probability_max": [10],
    },
}


async def test_forecast_validates_and_maps_open_meteo_payload() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_FORECAST)

    client = OpenMeteoWeather(transport=httpx.MockTransport(handler))

    report = await client.forecast(_BERLIN, days=1)

    assert report.temperature_c == 24.1
    assert report.description == "partly cloudy"
    assert [hour.time.strftime("%H:%M") for hour in report.hourly] == ["14:00"]


async def test_forecast_rejects_misaligned_provider_arrays() -> None:
    payload = {
        **_FORECAST,
        "hourly": {**_FORECAST["hourly"], "weather_code": [2]},
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = OpenMeteoWeather(transport=httpx.MockTransport(handler))

    with pytest.raises(ValueError, match="matching lengths"):
        await client.forecast(_BERLIN, days=1)
