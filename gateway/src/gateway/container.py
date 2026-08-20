from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider

from gateway.features import FEATURES
from gateway.features.conversation.application import AgentRunner
from gateway.features.conversation.infrastructure import RuntimeAgentRunner
from gateway.infrastructure import DatabaseProvider, SchedulerProvider
from gateway.presentation.gateway_di import GatewayProvider


class _AgentProvider(Provider):
    scope = Scope.APP

    @provide
    def agent(self) -> AgentRunner:
        return RuntimeAgentRunner()


def create_container() -> AsyncContainer:
    feature_providers = (
        provider() for feature in FEATURES for provider in feature.providers
    )
    return make_async_container(
        _AgentProvider(),
        DatabaseProvider(),
        SchedulerProvider(),
        GatewayProvider(),
        *feature_providers,
        FastapiProvider(),
    )
