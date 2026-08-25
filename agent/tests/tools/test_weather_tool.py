import asyncio
from datetime import datetime

from agenttoolkit import DependencyProvider, provide

from agent.tools import build_tools
from agent.tools.actions.weather import WeatherPeriod, _render_weather_report
from agent.tools.factory import _create_tools
from agent.tools.handler import LocationLookup
from agent.tools.handler.ports import (
    DailyForecast,
    HourlyForecast,
    Location,
    Weather,
    WeatherReport,
)

_HOME = Location(
    name="Berlin", latitude=52.52, longitude=13.405, timezone="Europe/Berlin"
)


def _report(name: str) -> WeatherReport:
    return WeatherReport(
        location_name=name,
        observed_at=datetime(2026, 7, 21, 13, 0),
        temperature_c=20.0,
        apparent_temperature_c=20.0,
        wind_speed_kmh=5.0,
        is_day=True,
        description="clear",
    )


def _hour(hour: int, *, day: int = 21, rain: int = 5, text: str = "clear"):
    return HourlyForecast(
        time=datetime(2026, 7, day, hour, 0),
        temperature_c=20.0 + hour / 10,
        precipitation_probability=rain,
        description=text,
    )


class _StubClient(Weather):
    def __init__(self, *, locations: dict[str, Location] | None = None) -> None:
        self.forecast_calls: list[tuple[Location, int]] = []
        self.locate_calls: list[str] = []
        self._locations = locations or {}

    async def forecast(self, location: Location, *, days: int) -> WeatherReport:
        self.forecast_calls.append((location, days))
        return _report(location.name)

    async def locate(self, query: str) -> Location | None:
        self.locate_calls.append(query)
        return self._locations.get(query)


class _StubLocationClient(LocationLookup):
    def __init__(self, location: Location) -> None:
        self._location = location
        self.calls = 0

    async def current(self) -> Location:
        self.calls += 1
        return self._location


class _Dependencies(DependencyProvider):
    def __init__(self, weather: Weather, location_lookup: LocationLookup) -> None:
        self._weather = weather
        self._location_lookup = location_lookup

    @provide
    def weather(self) -> Weather:
        return self._weather

    @provide
    def location_lookup(self) -> LocationLookup:
        return self._location_lookup


def _tools(client: Weather, location_client: LocationLookup):
    return _create_tools(dependencies=(_Dependencies(client, location_client),))


def _render(report: WeatherReport) -> str:
    return _render_weather_report(report, WeatherPeriod.NOW, 3)


def test_render_weather_report_drops_apparent_temperature_when_close() -> None:
    assert "feels like" not in _render(_report("Berlin"))


def test_render_weather_report_includes_apparent_temperature_when_it_diverges() -> None:
    report = _report("Berlin").model_copy(
        update={"temperature_c": 24.1, "apparent_temperature_c": 22.0}
    )

    assert _render(report) == (
        "Weather in Berlin: 24 °C (feels like 22 °C), clear, wind 5 km/h."
    )


def test_render_weather_report_appends_hourly_outlook_and_rain_forecast() -> None:
    hourly = [_hour(14), _hour(15), _hour(16, rain=60, text="light rain")]
    report = _report("Berlin").model_copy(update={"hourly": hourly})

    assert _render(report) == (
        "Weather in Berlin: 20 °C, clear, wind 5 km/h.\n"
        "Next hours: 14:00 21 °C clear; 16:00 22 °C light rain, 60% rain\n"
        "Rain likely from 16:00 (60%)."
    )


def test_render_weather_report_reports_no_rain_when_none_expected() -> None:
    report = _report("Berlin").model_copy(update={"hourly": [_hour(14)]})

    assert _render(report).endswith("No rain expected.")


def test_render_tomorrow_only_covers_the_following_day() -> None:
    hourly = [_hour(14), _hour(8, day=22, text="foggy"), _hour(10, day=22)]
    report = _report("Berlin").model_copy(update={"hourly": hourly})

    rendered = _render_weather_report(report, WeatherPeriod.TOMORROW, 3)

    assert "Tomorrow: 08:00 21 °C foggy" in rendered
    assert "14:00" not in rendered


def test_render_days_uses_the_daily_outlook() -> None:
    daily = [
        DailyForecast(
            day=datetime(2026, 7, 21).date(),
            temperature_min_c=15.0,
            temperature_max_c=26.0,
            precipitation_probability=10,
            description="clear",
        ),
        DailyForecast(
            day=datetime(2026, 7, 22).date(),
            temperature_min_c=13.0,
            temperature_max_c=21.0,
            precipitation_probability=70,
            description="light rain",
        ),
    ]
    report = _report("Berlin").model_copy(update={"daily": daily})

    rendered = _render_weather_report(report, WeatherPeriod.DAYS, 2)

    assert rendered.endswith(
        "Outlook: Tue 15–26 °C clear; Wed 13–21 °C light rain, 70% rain"
    )


def test_weather_tool_is_registered_without_availability_checks() -> None:
    assert build_tools().get("weather_report") is not None


def test_weather_tool_description_lets_location_be_omitted() -> None:
    tools = _tools(_StubClient(), _StubLocationClient(_HOME))
    schema = next(
        item
        for item in tools.get_schema("openai")
        if item["function"]["name"] == "weather_report"
    )
    parameters = schema["function"]["parameters"]

    assert "location" in schema["function"]["description"]
    assert parameters["properties"].keys() == {"location", "period", "days"}
    assert parameters.get("required", []) == []


def test_weather_uses_the_ip_location_when_no_location_given() -> None:
    client = _StubClient()
    location_client = _StubLocationClient(_HOME)
    tools = _tools(client, location_client)

    result = asyncio.run(tools.execute("weather_report"))

    assert result == _render(_report("Berlin"))
    assert location_client.calls == 1
    assert client.forecast_calls == [(_HOME, 1)]
    assert client.locate_calls == []


def test_weather_uses_the_requested_location_when_given() -> None:
    munich = Location(
        name="München", latitude=48.14, longitude=11.58, timezone="Europe/Berlin"
    )
    client = _StubClient(locations={"München": munich})
    location_client = _StubLocationClient(_HOME)
    tools = _tools(client, location_client)

    result = asyncio.run(tools.execute("weather_report", {"location": "München"}))

    assert result == _render(_report("München"))
    assert location_client.calls == 0
    assert client.forecast_calls == [(munich, 1)]


def test_weather_requests_two_days_for_tomorrow() -> None:
    client = _StubClient()
    tools = _tools(client, _StubLocationClient(_HOME))

    asyncio.run(tools.execute("weather_report", {"period": "tomorrow"}))

    assert client.forecast_calls == [(_HOME, 2)]


def test_weather_requests_the_requested_number_of_days() -> None:
    client = _StubClient()
    tools = _tools(client, _StubLocationClient(_HOME))

    asyncio.run(tools.execute("weather_report", {"period": "days", "days": 5}))

    assert client.forecast_calls == [(_HOME, 5)]


def test_weather_fails_when_requested_location_is_not_found() -> None:
    client = _StubClient()
    location_client = _StubLocationClient(_HOME)
    tools = _tools(client, location_client)

    result = asyncio.run(tools.execute("weather_report", {"location": "Nirgendwo"}))

    assert result == "No place named 'Nirgendwo' was found."
    assert client.forecast_calls == []
