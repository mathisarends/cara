import asyncio

from agenttoolkit import DependencyProvider, provide

from agent.tools import build_tools
from agent.tools.factory import _create_tools
from agent.tools.handler.ports import SearchResponse, SearchResult, WebSearch


class _StubClient(WebSearch):
    def __init__(self, response: SearchResponse) -> None:
        self._response = response
        self.queries: list[tuple[str, int]] = []

    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        self.queries.append((query, max_results))
        return self._response


class _Dependencies(DependencyProvider):
    def __init__(self, client: WebSearch) -> None:
        self._client = client

    @provide
    def web_search(self) -> WebSearch:
        return self._client


def _tools(client: WebSearch):
    return _create_tools(dependencies=(_Dependencies(client),))


def test_web_search_tool_is_registered_without_availability_checks() -> None:
    assert build_tools().get("web_search") is not None


def test_web_search_returns_the_client_summary() -> None:
    response = SearchResponse(
        answer="Die Antwort.",
        results=[
            SearchResult(title="Titel", url="https://example.com", content="Inhalt")
        ],
    )
    client = _StubClient(response)
    tools = _tools(client)

    result = asyncio.run(tools.execute("web_search", {"query": "Testfrage"}))

    assert result == response.summary()
    assert client.queries == [("Testfrage", 5)]


def test_web_search_forwards_max_results() -> None:
    client = _StubClient(SearchResponse())
    tools = _tools(client)

    asyncio.run(tools.execute("web_search", {"query": "Testfrage", "max_results": 2}))

    assert client.queries == [("Testfrage", 2)]
