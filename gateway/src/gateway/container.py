from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider

from cara_agent_plugin_api import AgentRunner
from gateway.features import FEATURES, gateway_protocol
from gateway.features.conversation.infrastructure import EchoAgentRunner
from gateway.infrastructure import DatabaseProvider, SchedulerProvider
from gateway.presentation.websocket import GatewayProvider


class _AgentProvider(Provider):
    scope = Scope.APP

    # Swap for RuntimeAgentRunner once the gateway drives the real agent.
    @provide
    def agent(self) -> AgentRunner:
        return EchoAgentRunner()


def create_container() -> AsyncContainer:
    feature_providers = (
        provider() for feature in FEATURES for provider in feature.providers
    )
    return make_async_container(
        _AgentProvider(),
        DatabaseProvider(),
        SchedulerProvider(),
        GatewayProvider(gateway_protocol()),
        *feature_providers,
        FastapiProvider(),
    )
