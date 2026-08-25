from collections.abc import Mapping
from typing import Any

from agent.configuration import AgentSettings
from agent.factory import AgentFactory
from agent_plugin_api import (
    AGENT_PLUGIN_API_VERSION,
    AgentPlugin,
    AgentPluginContext,
)

from .runner import CaraAgentRunner

__all__ = ["create_plugin"]


class _CaraAgentPlugin:
    api_version = AGENT_PLUGIN_API_VERSION

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> CaraAgentRunner:
        settings = AgentSettings.model_validate(dict(config))
        return CaraAgentRunner(context.sessions, AgentFactory(settings))


def create_plugin() -> AgentPlugin:
    return _CaraAgentPlugin()
