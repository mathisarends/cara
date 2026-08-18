from collections.abc import AsyncIterator
from enum import StrEnum

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

_PROMPT_CACHE_KEY = "cara"


class CodexModel(StrEnum):
    SPARK = "gpt-5.3-codex-spark"
    TERRA = "gpt-5.6-terra"
    SOL = "gpt-5.6-sol"


class CodexReasoningEffort(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


def create_codex_model(
    model: CodexModel,
    reasoning_effort: CodexReasoningEffort = CodexReasoningEffort.MEDIUM,
) -> ChatCodex:
    """Create Cara's Codex client with its Responses features enabled."""
    return ChatCodex.from_cli(
        model=model.value,
        reasoning_effort=reasoning_effort.value,
        reasoning_summary="auto",
        reasoning={"context": "all_turns"},
        continuation_mode=ContinuationMode.PREVIOUS_RESPONSE_ID,
        preserve_reasoning=True,
        prompt_cache_key=_PROMPT_CACHE_KEY,
        transport=HTTPResponsesTransport(),
    )


class CodexSession:
    def __init__(
        self,
        model: CodexModel = CodexModel.SPARK,
        *,
        reasoning_effort: CodexReasoningEffort = CodexReasoningEffort.LOW,
        instructions: str | None = None,
    ) -> None:
        self._model = create_codex_model(model, reasoning_effort)
        self._messages: list[Message] = []
        if instructions is not None:
            self._messages.append(SystemMessage(content=instructions))

    async def stream(self, text: str) -> AsyncIterator[str]:
        self._messages.append(UserMessage(content=text))
        reply = ""
        async for event in self._model.stream(messages=self._messages):
            if isinstance(event, StreamTextDelta) and event.delta:
                reply += event.delta
                yield event.delta
        self._messages.append(AssistantMessage(content=reply))
