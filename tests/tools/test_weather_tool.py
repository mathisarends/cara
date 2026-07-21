import asyncio

from cara.tools import Tools
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


def _tools(client: OpenMeteoClient, location_client: IpLocationClient) -> Tools:
    tools = Tools()
    tools.provide(client, location_client)
    return tools


def test_weather_tool_is_registered_without_availability_checks() -> None:
    assert Tools().get("weather") is not None


def test_weather_tool_description_uses_the_current_location_implicitly() -> None:
    tools = _tools(_StubClient(), _StubLocationClient(_HOME))
    schema = next(item for item in tools.to_schema() if item["function"]["name"] == "weather")

    assert schema["function"]["description"] == "Frage das aktuelle Wetter ab. Uses the current location."
    assert schema["function"]["parameters"] == {"type": "object", "properties": {}, "required": []}


def test_weather_uses_the_ip_location() -> None:
    client = _StubClient()
    location_client = _StubLocationClient(_HOME)
    tools = _tools(client, location_client)

    result = asyncio.run(tools.execute("weather"))

    assert result.ok
    assert result.content == _report("Berlin").summary()
    assert location_client.calls == 1
    assert client.current_calls == [_HOME]
