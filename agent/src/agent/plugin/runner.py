import asyncio
from collections.abc import AsyncIterator

from agent.agent import Agent
from agent.factory import AgentFactory
from agent.plugin.capabilities import turn_tool_dependencies
from agent.plugin.mapping import context_messages, plugin_event
from agent_plugin_api import (
    AgentEvent,
    AgentRunRequest,
    AgentSessionReader,
)


class CaraAgentRunner:
    def __init__(
        self,
        sessions: AgentSessionReader,
        agent_factory: AgentFactory,
    ) -> None:
        self._sessions = sessions
        self._agent_factory = agent_factory
        self._active_agents: set[Agent] = set()

    async def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        context = await self._sessions.context_for_turn(
            request.session.id,
            request.input_id,
        )
        agent = await self._agent_factory.create(
            context_messages(context),
            tool_dependencies=turn_tool_dependencies(request),
        )
        self._active_agents.add(agent)
        try:
            events = await agent.start_turn(request.input)
            async for event in events:
                yield plugin_event(event)
        finally:
            self._active_agents.discard(agent)
            await agent.interrupt()

    async def close(self) -> None:
        agents = tuple(self._active_agents)
        if agents:
            await asyncio.gather(*(agent.interrupt() for agent in agents))
