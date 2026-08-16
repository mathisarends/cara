from collections.abc import AsyncIterator
from typing import Protocol


class LanguageModel(Protocol):
    def respond(self, text: str) -> AsyncIterator[str]: ...
