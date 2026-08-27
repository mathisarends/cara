from unittest.mock import patch

from llmify import ChatCodex, WebSocketResponsesTransport

from llm.codex import (
    CodexModel,
    CodexReasoningEffort,
    create_codex_model,
)


def test_create_codex_model_passes_configured_options() -> None:
    with patch.object(ChatCodex, "from_cli", return_value=object()) as from_cli:
        create_codex_model(
            CodexModel.LUNA,
            reasoning_effort=CodexReasoningEffort.HIGH,
        )

    from_cli.assert_called_once_with(
        model="gpt-5.6-luna",
        reasoning_effort="high",
        transport=from_cli.call_args.kwargs["transport"],
    )
    assert isinstance(
        from_cli.call_args.kwargs["transport"], WebSocketResponsesTransport
    )


def test_create_codex_model_omits_unconfigured_options() -> None:
    with patch.object(ChatCodex, "from_cli", return_value=object()) as from_cli:
        create_codex_model(CodexModel.SPARK)

    from_cli.assert_called_once_with(
        model="gpt-5.3-codex-spark",
        transport=from_cli.call_args.kwargs["transport"],
    )
    assert isinstance(
        from_cli.call_args.kwargs["transport"], WebSocketResponsesTransport
    )


def test_codex_enums_expose_the_supported_configuration_values() -> None:
    assert {model.value for model in CodexModel} == {
        "gpt-5.3-codex-spark",
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
        "gpt-5.5",
        "gpt-5.4",
    }
    assert {effort.value for effort in CodexReasoningEffort} == {
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    }
