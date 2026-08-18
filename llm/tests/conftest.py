from collections.abc import AsyncIterator

import pytest

from llm import OpenAIResponsesStreamEvent
from llm import codex as codex_module


class _CodexBackend:
    def __init__(self) -> None:
        self.events: list[OpenAIResponsesStreamEvent] = []
        self.messages: list[list[object]] = []
        self.stream_options: list[dict[str, object]] = []

    async def stream(
        self, *, messages: list[object], **options: object
    ) -> AsyncIterator[OpenAIResponsesStreamEvent]:
        self.messages.append(list(messages))
        self.stream_options.append(options)
        for event in self.events:
            yield event


@pytest.fixture
def codex_backend(monkeypatch) -> _CodexBackend:
    backend = _CodexBackend()

    def create(*args: object, **kwargs: object) -> _CodexBackend:
        return backend

    monkeypatch.setattr(codex_module, "create_codex_model", create)
    return backend
