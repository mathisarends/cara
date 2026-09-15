import asyncio
from typing import cast

from agent.models import ModelSwitch
from agent.tools import build_tools
from llm import ChatModel


class _Model:
    def __init__(self, name: str, reasoning_effort: str | None) -> None:
        self.name = name
        self.reasoning_effort = reasoning_effort


def _models(*, fail_name: str | None = None) -> ModelSwitch:
    def factory(name: str):
        def create(reasoning_effort: str | None) -> ChatModel:
            return cast(ChatModel, _Model(name, reasoning_effort))

        return create

    async def smoke_test(model: ChatModel) -> None:
        candidate = cast(_Model, model)
        if candidate.name == fail_name:
            raise RuntimeError("unavailable")

    return ModelSwitch.configurable(
        {"first": factory("first"), "second": factory("second")},
        default="first",
        reasoning_efforts=("low", "high"),
        smoke_test=smoke_test,
    )


def test_model_control_tools_expose_runtime_configuration() -> None:
    tools = build_tools(injected_dependencies=(_models(),))
    names = {schema.name for schema in tools.get_schema()}

    assert {
        "current_model",
        "list_models",
        "switch_model",
        "set_reasoning_effort",
    } <= names
    assert {"current_reasoning_effort", "list_reasoning_efforts"}.isdisjoint(names)


def test_agent_can_inspect_and_change_model_configuration() -> None:
    models = _models()
    tools = build_tools(injected_dependencies=(models,))

    before = asyncio.run(tools.execute("current_model", {}))
    options = asyncio.run(tools.execute("list_models", {}))
    switched = asyncio.run(
        tools.execute(
            "switch_model",
            {"name": "second", "reasoning_effort": "high"},
        )
    )
    after = asyncio.run(tools.execute("current_model", {}))

    assert before == "Model: first. Reasoning effort: default."
    assert options == ("Models: first, second. Reasoning efforts: default, low, high.")
    assert switched.startswith("Smoke test passed.")
    assert after == "Model: second. Reasoning effort: high."
    assert models.current_name == "second"
    assert models.current_reasoning_effort == "high"


def test_failed_smoke_test_keeps_current_model_configuration() -> None:
    models = _models(fail_name="second")
    active_model = models.current
    tools = build_tools(injected_dependencies=(models,))

    result = asyncio.run(tools.execute("switch_model", {"name": "second"}))

    assert result.startswith("Tool failed:")
    assert "failed its smoke test" in result
    assert models.current is active_model
    assert models.current_name == "first"
    assert models.current_reasoning_effort is None
