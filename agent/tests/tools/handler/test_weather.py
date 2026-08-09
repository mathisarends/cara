import asyncio
import json

import httpx

from agent.tools.handler.weather import Location, OpenMeteoClient, WeatherReport

_BERLIN = Location(
    name="Berlin", latitude=52.52, longitude=13.405, timezone="Europe/Berlin"
)

_FORECAST = {
    "current": {
        "time": "2026-07-21T14:00",
        "interval": 900,
        "temperature_2m": 24.1,
        "apparent_temperature": 22.0,
        "weather_code": 2,
        "wind_speed_10m": 11.3,
        "is_day": 1,
    },
    "hourly": {
        "time": ["2026-07-21T13:00", "2026-07-21T14:00", "2026-07-21T15:00"],
        "temperature_2m": [23.5, 24.1, 25.0],
        "weather_code": [2, 2, 61],
        "precipitation_probability": [5, 10, 60],
    },
}

_GEOCODING = {
    "results": [
        {
            "name": "Hamburg",
            "latitude": 53.55,
            "longitude": 9.99,
            "timezone": "Europe/Berlin",
            "country": "Deutschland",
        }
    ]
}


def _client(routes: dict[str, dict]) -> OpenMeteoClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=routes[request.url.path])

    return OpenMeteoClient(transport=httpx.MockTransport(handler))


def test_report_parses_forecast_payload_via_model_validate() -> None:
    report = WeatherReport.model_validate(
        {**_FORECAST["current"], "location_name": "Berlin"}
    )

    assert report.temperature_c == 24.1
    assert report.apparent_temperature_c == 22.0
    assert report.wind_speed_kmh == 11.3
    assert report.is_day is True
    assert report.description == "teils bewölkt"


def test_report_maps_unknown_weather_code_to_fallback() -> None:
    report = WeatherReport.model_validate(
        {**_FORECAST["current"], "weather_code": 123, "location_name": "Berlin"}
    )

    assert report.description == "unbekannte Wetterlage"


def test_current_returns_report_for_location() -> None:
    client = _client({"/v1/forecast": _FORECAST})

    report = asyncio.run(client.current(_BERLIN))

    assert report.temperature_c == 24.1
    assert report.description == "teils bewölkt"


def test_current_filters_hourly_entries_before_now() -> None:
    client = _client({"/v1/forecast": _FORECAST})

    report = asyncio.run(client.current(_BERLIN))

    assert [hour.time.strftime("%H:%M") for hour in report.hourly] == ["14:00", "15:00"]


def test_locate_resolves_first_geocoding_result() -> None:
    client = _client({"/v1/search": _GEOCODING})

    location = asyncio.run(client.locate("Hamburg"))

    assert location == Location(
        name="Hamburg", latitude=53.55, longitude=9.99, timezone="Europe/Berlin"
    )


def test_locate_returns_none_when_no_results() -> None:
    client = _client({"/v1/search": {}})

    assert asyncio.run(client.locate("Nirgendwo")) is None


def test_forecast_request_carries_location_coordinates() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.url.params)
        return httpx.Response(200, content=json.dumps(_FORECAST))

    client = OpenMeteoClient(transport=httpx.MockTransport(handler))
    asyncio.run(client.current(_BERLIN))

    assert captured["latitude"] == "52.52"
    assert captured["longitude"] == "13.405"
    assert captured["timezone"] == "Europe/Berlin"
