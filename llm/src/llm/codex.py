from enum import StrEnum

from llmify import ChatCodex


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
    reasoning_effort: CodexReasoningEffort | None = None,
) -> ChatCodex:
    """Create a Codex client from Cara's configured model options."""
    if reasoning_effort is None:
        return ChatCodex.from_cli(model=model.value)
    return ChatCodex.from_cli(
        model=model.value,
        reasoning_effort=reasoning_effort.value,
    )
