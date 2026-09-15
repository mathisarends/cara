from collections.abc import Sequence

from agenttoolkit import DependencyProvider, ToolContext, Tools
from agenttoolkit.dependency import DependencyContainer
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.tools import AgentTools
from agent.tools.factory import _create_tools
from agent.tools.factory import build_tools as _build_tools
from gateway.agent_runtime.tools.actions import register_tools
from gateway.agent_runtime.tools.handler import GatewayReminders
from gateway.features.automation.application import AutomationService
from gateway.features.conversation.application import AgentSessionRef
from gateway.shared import UnitOfWork


class GatewayToolSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CARA_GATEWAY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    owner_id: str = Field(default="local", min_length=1)


class TurnToolDependencies:
    """Creates host-owned tool bindings for one conversation turn."""

    def __init__(
        self,
        automations: UnitOfWork[AutomationService],
        settings: GatewayToolSettings,
    ) -> None:
        self._automations = automations
        self._settings = settings

    def create(self, session: AgentSessionRef) -> tuple[object, ...]:
        owner_id = session.channel.account_id or self._settings.owner_id
        return (
            GatewayReminders(
                self._automations,
                owner_id=owner_id,
                session_id=session.id,
                channel=session.channel.name,
                channel_scoped=session.inactivity_timeout is not None,
            ),
        )


def build_tools(
    *,
    context: ToolContext,
    additional_tools: Tools | None = None,
    container: DependencyContainer | None = None,
) -> AgentTools:
    """Build the gateway's concrete tool catalog for focused tests and hosts."""
    return _build_tools(
        context=context,
        additional_tools=additional_tools,
        container=container,
        registrars=(register_tools,),
    )


def create_tools(
    context: ToolContext,
    *,
    container: DependencyContainer | None = None,
    dependencies: Sequence[DependencyProvider] | None = None,
) -> AgentTools:
    tools = _create_tools(
        context,
        container=container,
        dependencies=dependencies,
    )
    register_tools(tools)
    return tools
