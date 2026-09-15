import httpx
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from tavily import AsyncTavilyClient

from cara_tools.search.models import SearchResponse


class TavilyCredentials(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAVILY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: SecretStr = Field(min_length=1)


class TavilyWebSearch:
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
