from mcp import Client

from cara_tools.server import mcp


async def test_server_exposes_information_tools() -> None:
    async with Client(mcp) as client:
        response = await client.list_tools()

    assert {tool.name for tool in response.tools} == {"search", "weather"}
    weather = next(tool for tool in response.tools if tool.name == "weather")
    assert weather.input_schema["properties"].keys() == {"params"}
    params = weather.input_schema["$defs"]["WeatherParams"]
    assert params["properties"].keys() == {"location", "period", "days"}
    assert params["additionalProperties"] is False

    search = next(tool for tool in response.tools if tool.name == "search")
    assert search.input_schema["properties"].keys() == {"params"}
