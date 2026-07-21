import asyncio

from cara.tools import Tools
from cara.tools.handler.weather import Location, OpenMeteoClient, WeatherReport

_HOME = Location(name="Berlin", latitude=52.52, longitude=13.405, timezone="Europe/Berlin")
_ELSEWHERE = Location(name="Hamburg", latitude=53.55, longitude=9.99, timezone="Europe/Berlin")


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
    def __init__(self, located: Location | None = None) -> None:
        super().__init__()
        self._located = located
        self.current_calls: list[Location] = []
        self.locate_calls: list[str] = []

    async def locate(self, query: str) -> Location | None:
        self.locate_calls.append(query)
        return self._located

    async def current(self, location: Location) -> WeatherReport:
        self.current_calls.append(location)
        return _report(location.name)


def _tools(client: OpenMeteoClient) -> Tools:
    tools = Tools()
    tools.provide(_HOME, client)
    return tools


def test_weather_tool_is_unavailable_without_client_and_location() -> None:
    assert Tools().get("weather") is None


def test_weather_tool_is_available_once_client_and_location_are_provided() -> None:
    assert _tools(_StubClient()).get("weather") is not None


def test_weather_without_location_uses_the_configured_home() -> None:
    client = _StubClient()
    tools = _tools(client)

    result = asyncio.run(tools.execute("weather"))

    assert result.ok
    assert result.content == _report("Berlin").summary()
    assert client.current_calls == [_HOME]
    assert client.locate_calls == []


def test_weather_with_location_resolves_it_before_fetching() -> None:
    client = _StubClient(located=_ELSEWHERE)
    tools = _tools(client)

    result = asyncio.run(tools.execute("weather", {"location": "Hamburg"}))

    assert result.ok
    assert client.locate_calls == ["Hamburg"]
    assert client.current_calls == [_ELSEWHERE]


def test_weather_reports_an_unknown_location_back_to_the_model() -> None:
    client = _StubClient(located=None)
    tools = _tools(client)

    result = asyncio.run(tools.execute("weather", {"location": "Nirgendwo"}))

    assert not result.ok
    assert "Nirgendwo" in (result.content or "")
    assert client.current_calls == []
