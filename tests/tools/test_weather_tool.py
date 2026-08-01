import asyncio

from cara.tools import create_tool_context, create_tools
from cara.tools.handler import IpLocationClient
from cara.tools.handler.weather import Location, OpenMeteoClient, WeatherReport

_HOME = Location(name="Berlin", latitude=52.52, longitude=13.405, timezone="Europe/Berlin")


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
    def __init__(self) -> None:
        super().__init__()
        self.current_calls: list[Location] = []

    async def current(self, location: Location) -> WeatherReport:
        self.current_calls.append(location)
        return _report(location.name)


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


def test_weather_tool_is_registered_without_availability_checks() -> None:
    assert create_tools().get("weather_report") is not None


def test_weather_tool_description_uses_the_current_location_implicitly() -> None:
    tools = _tools(_StubClient(), _StubLocationClient(_HOME))
    schema = next(item for item in tools.get_schema("openai") if item["function"]["name"] == "weather_report")

    assert schema["function"]["description"] == "Frage das aktuelle Wetter ab. Uses the current location."
    assert schema["function"]["parameters"] == {
        "additionalProperties": False,
        "properties": {},
        "title": "WeatherParams",
        "type": "object",
    }


def test_weather_uses_the_ip_location() -> None:
    client = _StubClient()
    location_client = _StubLocationClient(_HOME)
    tools = _tools(client, location_client)

    result = asyncio.run(tools.execute("weather_report"))

    assert result.ok
    assert result.result == _report("Berlin").summary()
    assert location_client.calls == 1
    assert client.current_calls == [_HOME]
