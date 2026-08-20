from agenttoolkit import Inject, Tools
from pydantic import Field

from agent.tools.handler import WebSearch
from agent.tools.params import ToolParams


class WebSearchParams(ToolParams):
    query: str = Field(description="Search query for the web search.")
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of search results.",
    )


def register_web_search_tools(tools: Tools) -> None:
    @tools.action(
        description="Search the web for current information, news, or facts.",
        params=WebSearchParams,
    )
    async def web_search(params: WebSearchParams, websearch: Inject[WebSearch]) -> str:
        response = await websearch.search(params.query, max_results=params.max_results)
        return response.summary()
