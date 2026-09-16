from dishka import Provider, Scope, provide

from .factory import ModelSwitchFactory
from .settings import LlmSettings


class LlmProvider(Provider):
    scope = Scope.APP

    @provide
    def model_switch_factory(self, settings: LlmSettings) -> ModelSwitchFactory:
        return ModelSwitchFactory(settings)
