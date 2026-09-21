from collections.abc import AsyncIterator

from voice.barge_in.port import BargeInSignal, BargeInStrategy


class NoBargeIn(BargeInStrategy):
    """Lets the assistant always finish its turn."""

    async def signals(self) -> AsyncIterator[BargeInSignal]:
        return
        yield  # Unreachable, but makes this an empty async generator.
