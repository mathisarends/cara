from collections.abc import AsyncIterator

from llm import CodexModel, CodexReasoningEffort, CodexSession, StreamTextDelta
from voice.llm.events import AgentEvent, TextDelta, TurnCompleted

_INSTRUCTIONS = (
    "You are a conversational partner in a voice dialog. "
    "Reply very concisely: one to two short sentences, "
    "no lists, no markdown, no filler phrases. "
    "Always respond in English."
)


class CodexAgentSession:
    def __init__(self, model: CodexModel = CodexModel.SPARK) -> None:
        self._session = CodexSession(
            model,
            reasoning_effort=CodexReasoningEffort.LOW,
            instructions=_INSTRUCTIONS,
        )

    async def start_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        return self._stream_turn(text)

    async def _stream_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        async for event in self._session.stream(text):
            if isinstance(event, StreamTextDelta) and event.delta:
                yield TextDelta(event.delta)
        yield TurnCompleted()

    async def steer(self, text: str) -> None:
        pass

    async def interrupt(self) -> None:
        pass
