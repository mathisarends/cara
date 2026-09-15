from agenttoolkit import DependencyProvider, provide

from gateway.agent_runtime.tools.handler import (
    IpLocationLookup,
    LocationLookup,
    OpenMeteoWeather,
    Weather,
    WebSearch,
)
from gateway.agent_runtime.tools.handler.web_search import (
    TavilyCredentials,
    TavilyWebSearch,
)


class GatewayToolDependencies(DependencyProvider):
    """Default production adapters for Weather, LocationLookup, and WebSearch.

    Each dependency is resolved lazily and cached by the container the first
    time a tool actually needs it, so building the tool catalog never
    requires TAVILY_API_KEY to be set.
    """

    @provide
    def location_lookup(self) -> LocationLookup:
        return IpLocationLookup()

    @provide
    def weather(self) -> Weather:
        return OpenMeteoWeather()

    @provide
    def tavily_credentials(self) -> TavilyCredentials:
        return TavilyCredentials()

    @provide
    def web_search(self, credentials: TavilyCredentials) -> WebSearch:
        return TavilyWebSearch(credentials=credentials)
