import httpx
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from tavily import AsyncTavilyClient

from agent.tools.handler.ports import SearchResponse, WebSearch


class TavilyCredentials(BaseSettings):
    """Tavily credentials loaded from the environment and a local .env file."""

    model_config = SettingsConfigDict(
        env_prefix="TAVILY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: SecretStr


class TavilyWebSearch(WebSearch):
    """Web search via the Tavily API.

    Credentials are resolved lazily on the first search, not at construction,
    so building the tool catalog doesn't require TAVILY_API_KEY to be set.
    """

    def __init__(
        self,
        *,
        credentials: TavilyCredentials | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._credentials = credentials
        self._http_client = client
        self._tavily: AsyncTavilyClient | None = None

    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        data = await self._tavily_client().search(
            query, max_results=max_results, include_answer=True
        )
        return SearchResponse.model_validate(data)

    def _tavily_client(self) -> AsyncTavilyClient:
        if self._tavily is None:
            credentials = self._credentials or TavilyCredentials()
            self._tavily = AsyncTavilyClient(
                api_key=credentials.api_key.get_secret_value(),
                client=self._http_client,
            )
        return self._tavily
