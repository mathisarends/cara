from collections.abc import AsyncIterator
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx
from llmify import (
    AssistantMessage,
    ChatCodex,
    ContinuationMode,
    Message,
    PromptCacheOptions,
    ReasoningEffort,
    ResponsesOptions,
    ResponsesTransport,
    RetryCallback,
    StreamTextDelta,
    StreamToolCall,
    SystemMessage,
    ToolCall,
    UserMessage,
)
from llmify.providers.openai_responses_types import (
    OpenAIResponsesStreamEvent,
    ReasoningSummary,
)


class CodexModel(StrEnum):
    SPARK = "gpt-5.3-codex-spark"
    LUNA = "gpt-5.6-luna"
    TERRA = "gpt-5.6-terra"
    SOL = "gpt-5.6-sol"
    GPT_5_5 = "gpt-5.5"
    GPT_5_4 = "gpt-5.4"


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
    *,
    auth_path: Path | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    reasoning_effort: CodexReasoningEffort | ReasoningEffort | None = None,
    reasoning: dict[str, Any] | None = None,
    store: bool = False,
    transport: ResponsesTransport | None = None,
    responses_options: ResponsesOptions | None = None,
    continuation_mode: ContinuationMode = ContinuationMode.STATELESS,
    preserve_reasoning: bool = True,
    reasoning_summary: ReasoningSummary | None = None,
    prompt_cache_key: str | None = None,
    prompt_cache_options: PromptCacheOptions | None = None,
    timeout: float | httpx.Timeout | None = 60.0,
    max_retries: int = 2,
    on_retry: RetryCallback | None = None,
    default_headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> ChatCodex:
    """Create a Codex client with caller-selected model and Responses options."""
    if reasoning is not None:
        kwargs["reasoning"] = reasoning
    resolved_effort = (
        reasoning_effort.value
        if isinstance(reasoning_effort, CodexReasoningEffort)
        else reasoning_effort
    )
    return ChatCodex.from_cli(
        model=model.value,
        auth_path=auth_path,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        reasoning_effort=resolved_effort,
        store=store,
        transport=transport,
        responses_options=responses_options,
        continuation_mode=continuation_mode,
        preserve_reasoning=preserve_reasoning,
        reasoning_summary=reasoning_summary,
        prompt_cache_key=prompt_cache_key,
        prompt_cache_options=prompt_cache_options,
        timeout=timeout,
        max_retries=max_retries,
        on_retry=on_retry,
        default_headers=default_headers,
        **kwargs,
    )


class CodexSession:
    def __init__(
        self,
        model: CodexModel = CodexModel.SPARK,
        *,
        reasoning_effort: CodexReasoningEffort = CodexReasoningEffort.LOW,
        instructions: str | None = None,
        **model_options: Any,
    ) -> None:
        self._model = create_codex_model(
            model,
            reasoning_effort=reasoning_effort,
            **model_options,
        )
        self._messages: list[Message] = []
        if instructions is not None:
            self._messages.append(SystemMessage(content=instructions))

    async def stream(
        self,
        text: str,
        **stream_options: Any,
    ) -> AsyncIterator[OpenAIResponsesStreamEvent]:
        self._messages.append(UserMessage(content=text))
        reply = ""
        tool_calls: list[ToolCall] = []
        async for event in self._model.stream(
            messages=self._messages,
            **stream_options,
        ):
            if isinstance(event, StreamTextDelta) and event.delta:
                reply += event.delta
            elif isinstance(event, StreamToolCall):
                tool_calls.append(event.tool_call)
            yield event
        self._messages.append(AssistantMessage(content=reply, tool_calls=tool_calls))
