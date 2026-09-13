from collections.abc import AsyncIterator

from voice.barge_in.port import BargeInContext, BargeInSignal, BargeInStrategy


class NoBargeIn(BargeInStrategy):
    """Lets the assistant always finish its turn."""

    def set_context(self, context: BargeInContext) -> None:
        pass

    async def signals(self) -> AsyncIterator[BargeInSignal]:
        return
        yield  # Unreachable, but makes this an empty async generator.
