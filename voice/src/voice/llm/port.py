from collections.abc import AsyncIterator
from typing import Protocol


class ChatModel(Protocol):
    def respond(self, text: str) -> AsyncIterator[str]: ...
