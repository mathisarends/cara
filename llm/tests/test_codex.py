from unittest.mock import patch

from llmify import ChatCodex, HTTPResponsesTransport

from llm.codex import CodexModel, CodexReasoningEffort, create_codex_model


def test_create_codex_model_configures_responses_features() -> None:
    with patch.object(ChatCodex, "from_cli", return_value=object()) as from_cli:
        create_codex_model(CodexModel.SOL, CodexReasoningEffort.HIGH)

    options = from_cli.call_args.kwargs
    assert options["model"] == "gpt-5.6-sol"
    assert options["reasoning_effort"] == "high"
    assert options["reasoning_summary"] == "auto"
    assert options["reasoning"] == {"context": "all_turns"}
    assert options["continuation_mode"] == "previous_response_id"
    assert options["preserve_reasoning"] is True
    assert options["prompt_cache_key"] == "cara"
    assert isinstance(options["transport"], HTTPResponsesTransport)


def test_codex_enums_expose_the_supported_configuration_values() -> None:
    assert {model.value for model in CodexModel} == {"gpt-5.6-terra", "gpt-5.6-sol"}
    assert {effort.value for effort in CodexReasoningEffort} == {
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    }
