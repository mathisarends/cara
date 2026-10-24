from dishka.integrations.fastapi import FastapiProvider
from fastapi_canon import Feature

from gateway.agent_runtime.provider import AgentRuntimeProvider
from gateway.platform import DatabaseProvider, StorageProvider

platform_feature = Feature(
    name="platform",
    providers=[
        AgentRuntimeProvider,
        DatabaseProvider,
        StorageProvider,
        FastapiProvider,
    ],
)
