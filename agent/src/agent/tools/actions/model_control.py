from typing import Literal

from agenttoolkit import Inject, Tools, requires
from pydantic import Field

from agent.models import ModelSwitch
from agent.tools.middleware import ToolError
from agent.tools.params import ToolParams
from llm import CodexReasoningEffort

type _ReasoningEffortSelection = CodexReasoningEffort | Literal["default"]


class _SwitchModelParams(ToolParams):
    name: str = Field(description="Name of the model to switch to, exactly as listed.")
    reasoning_effort: _ReasoningEffortSelection | None = Field(
        default=None,
        description=(
            "Optional reasoning effort to use with the new model. "
            "Use 'default' for the provider default."
        ),
    )


class _SetReasoningEffortParams(ToolParams):
    reasoning_effort: _ReasoningEffortSelection = Field(
        description="Reasoning effort to activate, or 'default'."
    )


def register_model_control_tools(tools: Tools) -> None:
    alternatives_available = requires(
        ModelSwitch, predicate=lambda models: models.has_alternatives
    )
    reasoning_available = requires(
        ModelSwitch, predicate=lambda models: models.supports_reasoning_effort
    )
    model_control_available = requires(
        ModelSwitch,
        predicate=lambda models: (
            models.has_alternatives or models.supports_reasoning_effort
        ),
    )

    @tools.action(
        description=(
            "Get the model and reasoning effort currently driving this conversation."
        ),
        available_when=model_control_available,
    )
    async def current_model(models: Inject[ModelSwitch]) -> str:
        effort = models.current_reasoning_effort or "default"
        return f"Model: {models.current_name}. Reasoning effort: {effort}."

    @tools.action(
        description=(
            "List the models and reasoning efforts available for runtime selection."
        ),
        available_when=model_control_available,
    )
    async def list_models(models: Inject[ModelSwitch]) -> str:
        names = ", ".join(models.names)
        efforts = ", ".join(("default", *models.reasoning_efforts))
        return f"Models: {names}. Reasoning efforts: {efforts}."

    @tools.action(
        description=(
            "Smoke-test and then switch the model driving this conversation. "
            "The current model remains active if validation fails."
        ),
        params=_SwitchModelParams,
        available_when=alternatives_available,
    )
    async def switch_model(
        params: _SwitchModelParams, models: Inject[ModelSwitch]
    ) -> str:
        try:
            if params.reasoning_effort is None:
                await models.switch(params.name)
            else:
                await models.switch_with_reasoning_effort(
                    params.name,
                    _resolve_reasoning_effort(params.reasoning_effort),
                )
        except (RuntimeError, ValueError) as error:
            raise ToolError(str(error)) from None
        effort = models.current_reasoning_effort or "default"
        return (
            f"Smoke test passed. Switched to {params.name} "
            f"with reasoning effort {effort}."
        )

    @tools.action(
        description=(
            "Smoke-test and then change the active model's reasoning effort. "
            "The current configuration remains active if validation fails."
        ),
        params=_SetReasoningEffortParams,
        available_when=reasoning_available,
    )
    async def set_reasoning_effort(
        params: _SetReasoningEffortParams,
        models: Inject[ModelSwitch],
    ) -> str:
        try:
            await models.set_reasoning_effort(
                _resolve_reasoning_effort(params.reasoning_effort)
            )
        except (RuntimeError, ValueError) as error:
            raise ToolError(str(error)) from None
        effort = models.current_reasoning_effort or "default"
        return f"Smoke test passed. Reasoning effort is now {effort}."


def _resolve_reasoning_effort(
    reasoning_effort: _ReasoningEffortSelection,
) -> str | None:
    return None if reasoning_effort == "default" else reasoning_effort.value
