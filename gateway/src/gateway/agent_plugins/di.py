from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from agent_plugin_api import (
    AgentPluginContext,
    AgentRunner,
    AgentSessionReader,
)
from gateway.agent_plugins.loader import load_agent_plugin
from gateway.agent_plugins.settings import AgentPluginSettings, GatewaySettings


class AgentPluginProvider(Provider):
    scope = Scope.APP

    @provide
    def gateway_settings(self) -> GatewaySettings:
        return GatewaySettings()

    @provide
    def agent_settings(self, settings: GatewaySettings) -> AgentPluginSettings:
        return settings.agent

    @provide
    def plugin_context(self, sessions: AgentSessionReader) -> AgentPluginContext:
        return AgentPluginContext(sessions=sessions)

    @provide
    async def agent(
        self,
        settings: AgentPluginSettings,
        context: AgentPluginContext,
    ) -> AsyncIterator[AgentRunner]:
        plugin = load_agent_plugin(settings.plugin)
        runner = plugin.create(settings.config, context)
        if not isinstance(runner, AgentRunner):
            raise TypeError(
                f"Agent plugin '{settings.plugin}' returned an invalid runner"
            )
        try:
            yield runner
        finally:
            await runner.close()
