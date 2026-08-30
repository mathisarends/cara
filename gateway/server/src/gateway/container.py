from dishka import AsyncContainer, make_async_container
from dishka.integrations.fastapi import FastapiProvider

from gateway.agent_plugins import AgentPluginProvider
from gateway.features import FEATURES, gateway_protocol
from gateway.infrastructure import DatabaseProvider
from gateway.presentation.websocket.provider import GatewayProvider


def create_container() -> AsyncContainer:
    feature_providers = (
        provider() for feature in FEATURES for provider in feature.providers
    )
    return make_async_container(
        AgentPluginProvider(),
        DatabaseProvider(),
        GatewayProvider(gateway_protocol()),
        *feature_providers,
        FastapiProvider(),
    )
