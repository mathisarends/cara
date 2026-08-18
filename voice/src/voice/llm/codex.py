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
    "You are a conversational partner in a voice dialog. "
    "Reply very concisely: one to two short sentences, "
    "no lists, no markdown, no filler phrases. "
    "Always respond in English."
)

_PROMPT_CACHE_KEY = "cara-voice"


class CodexAgentSession:
    def __init__(self, model: str = "gpt-5.3-codex-spark") -> None:
        self._llm = ChatCodex.from_cli(
            model=model,
            reasoning_effort="low",
            reasoning_summary="auto",
            continuation_mode=ContinuationMode.PREVIOUS_RESPONSE_ID,
            preserve_reasoning=True,
            prompt_cache_key=_PROMPT_CACHE_KEY,
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
