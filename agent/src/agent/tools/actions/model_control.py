from agenttoolkit import Inject, Tools, requires
from pydantic import Field

from agent.models import ModelSwitch
from agent.tools.middleware import ToolError
from agent.tools.params import ToolParams


class SwitchModelParams(ToolParams):
    name: str = Field(description="Name of the model to switch to, exactly as listed.")


def register_model_control_tools(tools: Tools) -> None:
    alternatives_available = requires(
        ModelSwitch, predicate=lambda models: models.has_alternatives
    )

    @tools.action(
        description="Get the name of the model currently driving this conversation.",
        available_when=alternatives_available,
    )
    async def current_model(models: Inject[ModelSwitch]) -> str:
        return models.current_name

    @tools.action(
        description="List the models available to switch to.",
        available_when=alternatives_available,
    )
    async def list_models(models: Inject[ModelSwitch]) -> str:
        return ", ".join(models.names)

    @tools.action(
        description="Switch the model driving this conversation.",
        params=SwitchModelParams,
        available_when=alternatives_available,
    )
    async def switch_model(
        params: SwitchModelParams, models: Inject[ModelSwitch]
    ) -> str:
        try:
            models.switch(params.name)
        except ValueError as error:
            raise ToolError(str(error)) from None
        return f"Switched to {params.name}."
