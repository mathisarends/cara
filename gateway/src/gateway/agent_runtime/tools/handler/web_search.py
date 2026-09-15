import httpx
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from tavily import AsyncTavilyClient

from gateway.agent_runtime.tools.handler.ports import SearchResponse, WebSearch


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
    """Web search via the Tavily API."""

    def __init__(
        self,
        *,
        credentials: TavilyCredentials,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._tavily = AsyncTavilyClient(
            api_key=credentials.api_key.get_secret_value(),
            client=client,
        )

    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        data = await self._tavily.search(
            query, max_results=max_results, include_answer=True
        )
        return SearchResponse.model_validate(data)
