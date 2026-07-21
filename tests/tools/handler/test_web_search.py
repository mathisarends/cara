import asyncio

import httpx

from cara.settings import TavilyCredentials
from cara.tools.handler.web_search import SearchResponse, TavilySearchClient

_RESULTS = {
    "query": "aktuelles wetter berlin",
    "answer": "In Berlin ist es aktuell sonnig.",
    "results": [
        {
            "title": "Wetter Berlin",
            "url": "https://example.com/wetter-berlin",
            "content": "Sonnig, 24 Grad.",
            "score": 0.9,
        }
    ],
}


def _client(payload: dict) -> TavilySearchClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return TavilySearchClient(
        credentials=TavilyCredentials(api_key="test-key"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_response_parses_results_and_answer() -> None:
    response = SearchResponse.model_validate(_RESULTS)

    assert response.answer == "In Berlin ist es aktuell sonnig."
    assert len(response.results) == 1
    assert response.results[0].title == "Wetter Berlin"


def test_summary_includes_answer_and_results() -> None:
    response = SearchResponse.model_validate(_RESULTS)

    summary = response.summary()

    assert "In Berlin ist es aktuell sonnig." in summary
    assert "Wetter Berlin (https://example.com/wetter-berlin): Sonnig, 24 Grad." in summary


def test_summary_reports_no_results_when_empty() -> None:
    response = SearchResponse()

    assert response.summary() == "Keine Ergebnisse gefunden."


def test_search_returns_parsed_response_from_api() -> None:
    client = _client(_RESULTS)

    response = asyncio.run(client.search("aktuelles wetter berlin"))

    assert response.answer == "In Berlin ist es aktuell sonnig."
    assert response.results[0].url == "https://example.com/wetter-berlin"
