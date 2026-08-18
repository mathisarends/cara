from collections.abc import AsyncIterator

import pytest

from llm import OpenAIResponsesStreamEvent
from voice.llm import codex as codex_module


class _CodexSession:
    def __init__(self) -> None:
        self.events: list[OpenAIResponsesStreamEvent] = []
        self.turns: list[str] = []
        self.args: tuple[object, ...] = ()
        self.kwargs: dict[str, object] = {}

    async def stream(self, text: str) -> AsyncIterator[OpenAIResponsesStreamEvent]:
        self.turns.append(text)
        for event in self.events:
            yield event


@pytest.fixture
def codex_session(monkeypatch) -> _CodexSession:
    session = _CodexSession()

    def create(*args: object, **kwargs: object) -> _CodexSession:
        session.args = args
        session.kwargs = kwargs
        return session

    monkeypatch.setattr(codex_module, "CodexSession", create)
    return session
