import asyncio
from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from agent.configuration import AgentSettings
from agent.factory import AgentFactory
from agent.workspace import resolve_workspace_root
from gateway.agent_runtime.mcp import McpTools
from gateway.agent_runtime.sandbox import WorkspaceSandboxClient
from gateway.agent_runtime.settings import GatewaySettings
from gateway.features.conversation.application import AgentRuntime
from gateway.features.conversation.domain import SessionRepository
from gateway.features.conversation.infrastructure.cara_runtime import CaraAgentRuntime


class AgentRuntimeProvider(Provider):
    scope = Scope.APP

    @provide
    def gateway_settings(self) -> GatewaySettings:
        return GatewaySettings()

    @provide
    def agent_settings(self, settings: GatewaySettings) -> AgentSettings:
        return settings.agent

    @provide
    async def sandbox_client(
        self,
        settings: GatewaySettings,
    ) -> AsyncIterator[WorkspaceSandboxClient]:
        root = resolve_workspace_root(settings.agent.workspace.root)
        client = WorkspaceSandboxClient(settings.sandbox, root)
        try:
            yield client
        finally:
            await client.aclose()

    @provide
    async def mcp_tools(self, settings: GatewaySettings) -> AsyncIterator[McpTools]:
        tools = McpTools(settings.tools)
        await tools.connect()
        try:
            yield tools
        finally:
            await tools.aclose()

    @provide
    def agent_factory(
        self,
        settings: AgentSettings,
        sandbox: WorkspaceSandboxClient,
        mcp_tools: McpTools,
    ) -> AgentFactory:
        return AgentFactory(
            settings,
            workspace=sandbox,
            command_runner=sandbox,
            additional_tools=mcp_tools,
        )

    @provide
    async def agent_runtime(
        self,
        sessions: SessionRepository,
        factory: AgentFactory,
        sandbox: WorkspaceSandboxClient,
    ) -> AsyncIterator[AgentRuntime]:
        runtime = CaraAgentRuntime(sessions, factory, sandbox)
        warmup = asyncio.create_task(sandbox.ensure(), name="workspace-sandbox-warmup")
        try:
            yield runtime
        finally:
            if not warmup.done():
                warmup.cancel()
            await asyncio.gather(warmup, return_exceptions=True)
            await runtime.close()
