from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from agent_plugin_api.events import AgentEvent
from agent_plugin_api.models import AgentContext, AgentRunRequest, AgentSessionRef

AGENT_PLUGIN_API_VERSION = 3


class AgentSessionReader(Protocol):
    async def context_for_turn(
        self,
        session_id: UUID,
        input_id: UUID | None,
    ) -> AgentContext: ...


@dataclass(frozen=True, slots=True)
class AgentPluginContext:
    sessions: AgentSessionReader


@runtime_checkable
class AgentRunner(Protocol):
    async def prepare(self, session: AgentSessionRef) -> None: ...

    def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]: ...

    async def steer(self, session: AgentSessionRef, text: str) -> None:
        """Queue text for the running turn; ignored when that turn already ended."""
        ...

    async def finish(self, session: AgentSessionRef) -> None: ...

    async def close(self) -> None: ...


@runtime_checkable
class AgentPlugin(Protocol):
    api_version: int

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> AgentRunner: ...


@runtime_checkable
class AgentPluginFactory(Protocol):
    def __call__(self) -> AgentPlugin: ...
