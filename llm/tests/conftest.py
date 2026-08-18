from collections.abc import AsyncIterator

import pytest

from llm import codex as codex_module


class _CodexBackend:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.messages: list[list[object]] = []

    async def stream(self, *, messages: list[object]) -> AsyncIterator[object]:
        self.messages.append(list(messages))
        for event in self.events:
            yield event


@pytest.fixture
def codex_backend(monkeypatch) -> _CodexBackend:
    backend = _CodexBackend()
    monkeypatch.setattr(codex_module, "create_codex_model", lambda *args: backend)
    return backend
