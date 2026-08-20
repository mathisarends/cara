from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from agent_plugin_api.events import AgentEvent
from agent_plugin_api.models import AgentContext, AgentRunRequest

AGENT_PLUGIN_API_VERSION = 1


class AgentSessionReader(Protocol):
    async def context_for_turn(
        self,
        session_id: UUID,
        input_id: UUID,
    ) -> AgentContext: ...


@dataclass(frozen=True, slots=True)
class AgentPluginContext:
    sessions: AgentSessionReader


@runtime_checkable
class AgentRunner(Protocol):
    def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]: ...

    async def close(self) -> None: ...


@runtime_checkable
class AgentPlugin(Protocol):
    api_version: int

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> AgentRunner: ...
