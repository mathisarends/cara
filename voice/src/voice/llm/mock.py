from collections.abc import AsyncIterator


class StreamingEchoLLM:
    """Streams its input back unchanged, one character at a time."""

    async def stream(self, text: str) -> AsyncIterator[str]:
        for character in text:
            yield character
