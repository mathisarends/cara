from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from cara_tools.search import SearchParams, TavilyCredentials, TavilyWebSearch
from cara_tools.weather import WeatherParams, weather_report

mcp = MCPServer("cara-tools", title="Cara information tools")


@mcp.tool()
async def weather(
    params: WeatherParams,
) -> str:
    """Look up current conditions or a forecast for a place."""
    return await weather_report(
        params.location,
        params.period,
        params.days,
    )


@mcp.tool()
async def search(
    params: SearchParams,
) -> str:
    """Search the web for current information, news, or facts."""
    credentials = TavilyCredentials()
    client = TavilyWebSearch(credentials=credentials)
    response = await client.search(
        params.query,
        max_results=params.max_results,
    )
    return response.summary()


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})
