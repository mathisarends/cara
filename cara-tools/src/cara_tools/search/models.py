from pydantic import BaseModel, ConfigDict, Field


class SearchResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    title: str
    url: str
    content: str


class SearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    results: tuple[SearchResult, ...] = Field(default_factory=tuple)
    answer: str | None = None

    def summary(self) -> str:
        if self.answer is None and not self.results:
            return "No results found."
        parts = [self.answer] if self.answer else []
        parts.extend(
            f"{result.title} ({result.url}): {result.content}"
            for result in self.results
        )
        return "\n\n".join(parts)


class SearchParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=1, description="Web search query.")
    max_results: int = Field(default=5, ge=1, le=10)
