from dishka.integrations.fastapi import FastapiProvider
from fastapi_canon import Feature

from gateway.agent_runtime import AgentRuntimeProvider
from gateway.platform import DatabaseProvider
from gateway.presentation.rpc.channels import gateway_channel
from gateway.presentation.websocket.provider import GatewayProvider
from gateway.presentation.websocket.router import gateway_router

platform_feature = Feature(
    name="platform",
    routers=[gateway_router],
    providers=[
        AgentRuntimeProvider,
        DatabaseProvider,
        lambda: GatewayProvider(gateway_channel()),
        FastapiProvider,
    ],
)
