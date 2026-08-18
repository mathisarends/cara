from collections.abc import AsyncIterator

from llmify import (
    AssistantMessage,
    ChatCodex,
    ContinuationMode,
    HTTPResponsesTransport,
    Message,
    StreamTextDelta,
    SystemMessage,
    UserMessage,
)

from voice.llm.events import AgentEvent, TextDelta, TurnCompleted

_INSTRUCTIONS = (
    "Du bist Gesprächspartner in einem Sprachdialog. "
    "Antworte sehr knapp: ein bis zwei kurze Sätze, "
    "keine Aufzählungen, kein Markdown, keine Floskeln."
)


class CodexAgentSession:
    def __init__(self, model: str = "gpt-5.3-codex-spark") -> None:
        self._llm = ChatCodex.from_cli(
            model=model,
            reasoning_effort="low",
            continuation_mode=ContinuationMode.PREVIOUS_RESPONSE_ID,
            transport=HTTPResponsesTransport(),
        )
        self._messages: list[Message] = [SystemMessage(content=_INSTRUCTIONS)]

    async def start_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        return self._stream_turn(text)

    async def _stream_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        self._messages.append(UserMessage(content=text))
        reply = ""
        async for event in self._llm.stream(messages=self._messages):
            if isinstance(event, StreamTextDelta) and event.delta:
                reply += event.delta
                yield TextDelta(event.delta)
        self._messages.append(AssistantMessage(content=reply))
        yield TurnCompleted()

    async def steer(self, text: str) -> None:
        pass

    async def interrupt(self) -> None:
        pass
