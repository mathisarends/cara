from dishka.integrations.fastapi import FastapiProvider
from fastapi_canon import Feature

from gateway.agent_runtime.provider import AgentRuntimeProvider
from gateway.platform import DatabaseProvider, StorageProvider
from gateway.presentation.websocket import GatewayProvider, gateway_router

platform_feature = Feature(
    name="platform",
    routers=[gateway_router],
    providers=[
        AgentRuntimeProvider,
        DatabaseProvider,
        StorageProvider,
        GatewayProvider,
        FastapiProvider,
    ],
)
