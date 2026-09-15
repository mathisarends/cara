from collections.abc import AsyncIterator, Sequence
from typing import cast
from uuid import uuid4

from agent.agent import Agent
from agent.events import TurnCompleted
from agent.factory import AgentFactory
from gateway.agent_runtime.tools import TurnToolDependencies
from gateway.features.conversation.application import (
    AgentChannelRef,
    AgentRunRequest,
    AgentSessionRef,
    ChatCompleted,
)
from gateway.features.conversation.domain import ChannelRef, Session, SessionRepository
from gateway.features.conversation.infrastructure.cara_runtime import CaraAgentRuntime
from llm import Message


class _Sessions:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def find_by_id(self, session_id):
        return self._session if session_id == self._session.id else None


class _Agent:
    def __init__(self) -> None:
        self.inputs: list[str] = []
        self.closed = False

    async def start_turn(self, text: str) -> AsyncIterator[object]:
        self.inputs.append(text)

        async def events():
            yield TurnCompleted(text)

        return events()

    async def steer(self, text: str) -> None:
        pass

    async def aclose(self) -> None:
        self.closed = True


class _Factory:
    def __init__(self) -> None:
        self.agents: list[_Agent] = []
        self.dependencies: list[Sequence[object]] = []

    async def create(
        self,
        messages: Sequence[Message] = (),
        *,
        tool_dependencies: Sequence[object] = (),
    ) -> Agent:
        del messages
        agent = _Agent()
        self.agents.append(agent)
        self.dependencies.append(tool_dependencies)
        return cast(Agent, agent)


class _Sandbox:
    def __init__(self) -> None:
        self.ensure_count = 0

    async def ensure(self) -> None:
        self.ensure_count += 1


class _TurnDependencies:
    def create(self, session: AgentSessionRef) -> tuple[object, ...]:
        return (session.id,)


async def test_runtime_reuses_one_agent_until_the_session_is_finished() -> None:
    session = Session.create(ChannelRef("voice"))
    session_ref = AgentSessionRef(session.id, AgentChannelRef("voice"))
    factory = _Factory()
    sandbox = _Sandbox()
    runtime = CaraAgentRuntime(
        cast(SessionRepository, _Sessions(session)),
        cast(AgentFactory, factory),
        sandbox,
        cast(TurnToolDependencies, _TurnDependencies()),
    )

    await runtime.prepare(session_ref)
    await runtime.prepare(session_ref)
    for text in ("first", "second"):
        request = AgentRunRequest(
            session=session_ref,
            turn_id=uuid4(),
            input_id=None,
            input=text,
        )
        events = [event async for event in runtime.run(request)]
        assert events == [ChatCompleted(text)]

    assert len(factory.agents) == 1
    assert factory.dependencies == [(session.id,)]
    assert factory.agents[0].inputs == ["first", "second"]
    assert sandbox.ensure_count == 2

    await runtime.finish(session_ref)
    assert factory.agents[0].closed
