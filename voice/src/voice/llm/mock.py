from collections.abc import AsyncIterator

from voice.llm.events import AgentEvent, TextDelta, TurnCompleted


class EchoAgentSession:
    """A deterministic agent session useful for examples and tests."""

    def __init__(self, prefix: str = "Your have said: ") -> None:
        self._prefix = prefix

    async def start_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        return self._stream_turn(text)

    async def _stream_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        for character in f"{self._prefix}{text}":
            yield TextDelta(character)
        yield TurnCompleted()

    async def steer(self, text: str) -> None:
        pass

    async def interrupt(self) -> None:
        pass
