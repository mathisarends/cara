from collections.abc import AsyncIterator

import pytest

from voice.llm import codex as codex_module


class _CodexBackend:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.config: dict[str, object] = {}
        self.messages: list[list[object]] = []

    async def stream(self, *, messages: list[object]) -> AsyncIterator[object]:
        self.messages.append(list(messages))
        for event in self.events:
            yield event


@pytest.fixture
def codex_backend(monkeypatch) -> _CodexBackend:
    backend = _CodexBackend()

    def create(**kwargs: object) -> _CodexBackend:
        backend.config = kwargs
        return backend

    monkeypatch.setattr(codex_module.ChatCodex, "from_cli", staticmethod(create))
    return backend
