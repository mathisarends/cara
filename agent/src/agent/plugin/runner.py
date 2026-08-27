import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

from llmify import ChatCodex

from agent.agent import Agent
from agent.factory import AgentFactory
from agent.plugin.capabilities import turn_tool_dependencies
from agent.plugin.mapping import context_messages, plugin_event
from agent_plugin_api import (
    AgentEvent,
    AgentRunRequest,
    AgentSessionReader,
    AgentSessionRef,
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
        self._preparations: dict[UUID, asyncio.Task[ChatCodex]] = {}
        self._preparation_lock = asyncio.Lock()

    async def prepare(self, session: AgentSessionRef) -> None:
        async with self._preparation_lock:
            preparation = self._preparations.get(session.id)
            if preparation is None:
                preparation = asyncio.create_task(
                    self._agent_factory.prewarm_model(),
                    name=f"cara-model-prewarm-{session.id}",
                )
                self._preparations[session.id] = preparation
        try:
            await asyncio.shield(preparation)
        except BaseException:
            async with self._preparation_lock:
                if self._preparations.get(session.id) is preparation:
                    self._preparations.pop(session.id)
            raise

    async def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        preparation = await self._take_preparation(request.session.id)
        initial_model = await preparation if preparation is not None else None
        context = await self._sessions.context_for_turn(
            request.session.id,
            request.input_id,
        )
        try:
            agent = await self._agent_factory.create(
                context_messages(context),
                tool_dependencies=turn_tool_dependencies(request),
                initial_model=initial_model,
            )
        except BaseException:
            if initial_model is not None:
                await initial_model.aclose()
            raise
        self._active_agents.add(agent)
        try:
            events = await agent.start_turn(request.input)
            async for event in events:
                yield plugin_event(event)
        finally:
            self._active_agents.discard(agent)
            await agent.aclose()

    async def finish(self, session: AgentSessionRef) -> None:
        preparation = await self._take_preparation(session.id)
        if preparation is None:
            return
        model = await preparation
        await model.aclose()

    async def close(self) -> None:
        async with self._preparation_lock:
            preparations = tuple(self._preparations.values())
            self._preparations.clear()
        prepared_models = await asyncio.gather(*preparations, return_exceptions=True)
        await asyncio.gather(
            *(
                model.aclose()
                for model in prepared_models
                if isinstance(model, ChatCodex)
            )
        )
        agents = tuple(self._active_agents)
        if agents:
            await asyncio.gather(*(agent.aclose() for agent in agents))

    async def _take_preparation(
        self,
        session_id: UUID,
    ) -> asyncio.Task[ChatCodex] | None:
        async with self._preparation_lock:
            return self._preparations.pop(session_id, None)
