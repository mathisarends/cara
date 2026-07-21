import httpx
from pydantic import BaseModel, ConfigDict, Field
from tavily import AsyncTavilyClient

from cara.settings import TavilyCredentials


class SearchResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    title: str
    url: str
    content: str


class SearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    results: list[SearchResult] = Field(default_factory=list)
    answer: str | None = None

    def summary(self) -> str:
        if self.answer is None and not self.results:
            return "Keine Ergebnisse gefunden."
        parts = [self.answer] if self.answer else []
        parts.extend(f"{result.title} ({result.url}): {result.content}" for result in self.results)
        return "\n\n".join(parts)


class TavilySearchClient:
    """Web search via the Tavily API."""

    def __init__(
        self,
        *,
        credentials: TavilyCredentials | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        credentials = credentials or TavilyCredentials()
        self._client = AsyncTavilyClient(api_key=credentials.api_key.get_secret_value(), client=client)

    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        data = await self._client.search(query, max_results=max_results, include_answer=True)
        return SearchResponse.model_validate(data)
