import asyncio
from datetime import datetime

from cara.tools import create_tool_context, create_tools
from cara.tools.catalog import _render_weather_report
from cara.tools.handler import IpLocationClient
from cara.tools.handler.weather import (
    HourlyForecast,
    Location,
    OpenMeteoClient,
    WeatherReport,
)

_HOME = Location(
    name="Berlin", latitude=52.52, longitude=13.405, timezone="Europe/Berlin"
)


def _report(name: str) -> WeatherReport:
    return WeatherReport(
        location_name=name,
        temperature_c=20.0,
        apparent_temperature_c=20.0,
        wind_speed_kmh=5.0,
        is_day=True,
        description="klar",
    )


class _StubClient(OpenMeteoClient):
    def __init__(self, *, locations: dict[str, Location] | None = None) -> None:
        super().__init__()
        self.current_calls: list[Location] = []
        self.locate_calls: list[str] = []
        self._locations = locations or {}

    async def current(self, location: Location) -> WeatherReport:
        self.current_calls.append(location)
        return _report(location.name)

    async def locate(self, query: str) -> Location | None:
        self.locate_calls.append(query)
        return self._locations.get(query)


class _StubLocationClient(IpLocationClient):
    def __init__(self, location: Location) -> None:
        super().__init__()
        self._location = location
        self.calls = 0

    async def current(self) -> Location:
        self.calls += 1
        return self._location


def _tools(client: OpenMeteoClient, location_client: IpLocationClient):
    return create_tools(create_tool_context(client, location_client))


def test_render_weather_report_drops_apparent_temperature_when_close() -> None:
    report = _report("Berlin").model_copy(update={"apparent_temperature_c": 20.0})

    assert "gefühlt" not in _render_weather_report(report)


def test_render_weather_report_includes_apparent_temperature_when_it_diverges() -> None:
    report = _report("Berlin").model_copy(
        update={"temperature_c": 24.1, "apparent_temperature_c": 22.0}
    )

    assert _render_weather_report(report) == (
        "## Wetter in Berlin\n\n**24 °C**, gefühlt 22 °C, klar, Wind 5 km/h."
    )


def test_render_weather_report_appends_hourly_outlook() -> None:
    hourly = [
        HourlyForecast(
            time=datetime(2026, 7, 21, 14, 0),
            temperature_c=24.1,
            precipitation_probability=10,
            description="teils bewölkt",
        ),
        HourlyForecast(
            time=datetime(2026, 7, 21, 15, 0),
            temperature_c=25.0,
            precipitation_probability=60,
            description="leichter Regen",
        ),
    ]
    report = _report("Berlin").model_copy(update={"hourly": hourly})

    rendered = _render_weather_report(report)

    assert rendered.endswith(
        "| Uhrzeit | Wetter | Temp | Regen |\n"
        "| --- | --- | --- | --- |\n"
        "| 14:00 | teils bewölkt | 24 °C | 10% |\n"
        "| 15:00 | leichter Regen | 25 °C | 60% |"
    )


def test_weather_tool_is_registered_without_availability_checks() -> None:
    assert create_tools().get("weather_report") is not None


def test_weather_tool_description_lets_location_be_omitted() -> None:
    tools = _tools(_StubClient(), _StubLocationClient(_HOME))
    schema = next(
        item
        for item in tools.get_schema("openai")
        if item["function"]["name"] == "weather_report"
    )

    assert "location" in schema["function"]["description"]
    assert schema["function"]["parameters"]["properties"].keys() == {"location"}
    assert "location" not in schema["function"]["parameters"].get("required", [])


def test_weather_uses_the_ip_location_when_no_location_given() -> None:
    client = _StubClient()
    location_client = _StubLocationClient(_HOME)
    tools = _tools(client, location_client)

    result = asyncio.run(tools.execute("weather_report"))

    assert result == _render_weather_report(_report("Berlin"))
    assert location_client.calls == 1
    assert client.current_calls == [_HOME]
    assert client.locate_calls == []


def test_weather_uses_the_requested_location_when_given() -> None:
    munich = Location(
        name="München", latitude=48.14, longitude=11.58, timezone="Europe/Berlin"
    )
    client = _StubClient(locations={"München": munich})
    location_client = _StubLocationClient(_HOME)
    tools = _tools(client, location_client)

    result = asyncio.run(tools.execute("weather_report", {"location": "München"}))

    assert result == _render_weather_report(_report("München"))
    assert location_client.calls == 0
    assert client.current_calls == [munich]


def test_weather_fails_when_requested_location_is_not_found() -> None:
    client = _StubClient()
    location_client = _StubLocationClient(_HOME)
    tools = _tools(client, location_client)

    result = asyncio.run(tools.execute("weather_report", {"location": "Nirgendwo"}))

    assert result == "Kein Ort namens 'Nirgendwo' gefunden."
    assert client.current_calls == []
