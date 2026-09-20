from collections.abc import Callable

from gateway.features.llm.application import ModelFactory, ModelSwitch
from llm import (
    ChatModel,
    CodexModel,
    CodexReasoningEffort,
    CodexTransport,
    create_codex_model,
)

from .settings import LlmSettings


class ModelSwitchFactory:
    def __init__(self, settings: LlmSettings) -> None:
        self._settings = settings

    def create(self) -> ModelSwitch:
        factories: dict[str, ModelFactory] = {
            model.value: _codex_model_factory(model, self._settings.transport)
            for model in self._settings.available
        }
        return ModelSwitch.configurable(
            factories,
            default=self._settings.default.value,
            reasoning_efforts=tuple(effort.value for effort in CodexReasoningEffort),
        )


def _codex_model_factory(
    configured_model: CodexModel,
    transport: CodexTransport,
) -> Callable[[str | None], ChatModel]:
    def create(reasoning_effort: str | None) -> ChatModel:
        if reasoning_effort is None:
            return create_codex_model(configured_model, transport=transport)
        return create_codex_model(
            configured_model,
            reasoning_effort=CodexReasoningEffort(reasoning_effort),
            transport=transport,
        )

    return create
