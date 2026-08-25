from collections.abc import Sequence
from typing import cast
from uuid import UUID

from agenttoolkit import Skills, ToolContext
from agenttoolkit.builtins import Workspace
from agenttoolkit.dependency import DependencyContainer
from llmify import Message

from agent.agent import Agent
from agent.configuration import AgentSettings
from agent.dependencies import ConfiguredDependencies
from agent.models import ModelSwitch
from agent.tools import build_tools
from agent.tools.dependency_provider import BuiltinDependencies
from agent.tools.handler import GatewayConnection, GatewayReminders, Reminders

_SKILLS_DEPENDENCY = cast(type[Skills | None], Skills | None)


class AgentFactory:
    """Build a fully configured agent without depending on a transport plugin."""

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings

    async def create(
        self,
        messages: Sequence[Message] = (),
        *,
        session_id: UUID | None = None,
        turn_id: UUID | None = None,
    ) -> Agent:
        container = DependencyContainer(
            ConfiguredDependencies(self._settings),
            BuiltinDependencies(),
        )
        settings = await container.get(AgentSettings)
        workspace = await container.get(Workspace)
        skills = await container.get(_SKILLS_DEPENDENCY)
        models = await container.get(ModelSwitch)
        tool_context = await container.get(ToolContext)
        tool_context.provide(_reminders(session_id, turn_id))
        tools = build_tools(
            context=tool_context,
            container=container,
        )
        return Agent(
            models=models,
            tools=tools,
            skills=skills,
            system_prompt=settings.system_prompt,
            workspace_root=workspace.root,
            messages=messages,
        )


def _reminders(session_id: UUID | None, turn_id: UUID | None) -> Reminders | None:
    """Reminder scheduling, available only to turns driven by the gateway."""
    if session_id is None or turn_id is None:
        return None
    connection = GatewayConnection()
    if connection.token is None:
        return None
    return GatewayReminders(connection, session_id=session_id, turn_id=turn_id)
