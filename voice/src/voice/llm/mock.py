from collections.abc import AsyncIterator


class EchoLanguageModel:
    """A deterministic streaming model useful for examples and tests."""

    def __init__(self, prefix: str = "Du hast gesagt: ") -> None:
        self._prefix = prefix

    async def respond(self, text: str) -> AsyncIterator[str]:
        for character in f"{self._prefix}{text}":
            yield character
