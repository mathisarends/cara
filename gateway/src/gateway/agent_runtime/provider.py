import asyncio
from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from agent.configuration import AgentSettings
from agent.factory import AgentFactory
from gateway.agent_runtime.mcp import McpTools
from gateway.agent_runtime.sandbox import WorkspaceSandboxClient
from gateway.agent_runtime.settings import GatewaySettings
from gateway.agent_runtime.tools import (
    GatewayToolSettings,
    TurnToolDependencies,
    register_tools,
)
from gateway.agent_runtime.workspace import resolve_workspace_root
from gateway.features.automation.application import AutomationService
from gateway.features.conversation.application import AgentRuntime, SessionService
from gateway.features.conversation.infrastructure.cara_runtime import CaraAgentRuntime
from gateway.shared import UnitOfWork


class AgentRuntimeProvider(Provider):
    scope = Scope.APP

    @provide
    def gateway_settings(self) -> GatewaySettings:
        return GatewaySettings()

    @provide
    def agent_settings(self, settings: GatewaySettings) -> AgentSettings:
        return settings.agent

    @provide
    def tool_settings(self) -> GatewayToolSettings:
        return GatewayToolSettings()

    @provide
    def turn_tool_dependencies(
        self,
        automations: UnitOfWork[AutomationService],
        settings: GatewayToolSettings,
    ) -> TurnToolDependencies:
        return TurnToolDependencies(automations, settings)

    @provide
    async def sandbox_client(
        self,
        settings: GatewaySettings,
    ) -> AsyncIterator[WorkspaceSandboxClient]:
        root = resolve_workspace_root(settings.workspace.root)
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
            tool_registrars=(register_tools,),
        )

    @provide
    async def agent_runtime(
        self,
        sessions: SessionService,
        factory: AgentFactory,
        sandbox: WorkspaceSandboxClient,
        tool_dependencies: TurnToolDependencies,
    ) -> AsyncIterator[AgentRuntime]:
        runtime = CaraAgentRuntime(sessions, factory, sandbox, tool_dependencies)
        warmup = asyncio.create_task(sandbox.ensure(), name="workspace-sandbox-warmup")
        try:
            yield runtime
        finally:
            if not warmup.done():
                warmup.cancel()
            await asyncio.gather(warmup, return_exceptions=True)
            await runtime.close()
