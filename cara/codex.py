from enum import StrEnum

from llmify import (
    ChatCodex,
    ContinuationMode,
    HTTPResponsesTransport,
)

_PROMPT_CACHE_KEY = "cara"


class CodexModel(StrEnum):
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
