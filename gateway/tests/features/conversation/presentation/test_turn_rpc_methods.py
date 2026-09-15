import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_plugin_api import (
    AgentEvent,
    AgentRunner,
    AgentRunRequest,
    AgentSessionRef,
    ChatCompleted,
)
from gateway.features.conversation.application import (
    ConversationEvent,
    ConversationEventType,
    EventPublisher,
    SessionService,
    TurnService,
)
from gateway.features.conversation.domain import SessionNotFoundError
from gateway.features.conversation.infrastructure.repository import (
    SQLSessionRepository,
)
from gateway.features.conversation.infrastructure.turn_lease import SQLTurnLease
from gateway.features.conversation.presentation.rpc.methods import (
    cancel_turn,
    create_session,
    finish_turn,
    get_session,
    prepare_turn,
    start_turn,
)
from gateway.features.conversation.presentation.rpc.models import (
    AssistantMessageItem,
    CreateSessionParams,
    SessionChannel,
    SessionParams,
    StartTurnParams,
)

_CHANNEL = SessionChannel(name="voice")


class _RecordingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.events: list[ConversationEvent] = []

    async def publish(self, event: ConversationEvent) -> None:
        self.events.append(event)


class _LifecycleAgentRunner(AgentRunner):
    def __init__(self) -> None:
        self.lifecycle: list[tuple[str, AgentSessionRef]] = []

    async def prepare(self, session: AgentSessionRef) -> None:
        self.lifecycle.append(("prepare", session))

    async def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        del request
        yield ChatCompleted("done", finish_reason="stop")

    async def finish(self, session: AgentSessionRef) -> None:
        self.lifecycle.append(("finish", session))

    async def close(self) -> None:
        pass


class _HangingAgentRunner(AgentRunner):
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        del request
        self.started.set()
        await asyncio.Event().wait()
        yield  # pragma: no cover

    async def close(self) -> None:
        pass


def _services(
    session_repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
    runner: AgentRunner,
    publisher: EventPublisher | None = None,
) -> tuple[SessionService, TurnService]:
    sessions = SessionService(session_repository)
    turns = TurnService(
        session_repository,
        sessions,
        SQLTurnLease(session_factory),
        publisher or _RecordingPublisher(),
        runner,
    )
    return sessions, turns


async def test_prepare_and_finish_turn_forward_the_session(
    session_repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    runner = _LifecycleAgentRunner()
    sessions, turns = _services(session_repository, session_factory, runner)
    created = await create_session(CreateSessionParams(channel=_CHANNEL), sessions)

    prepared = await prepare_turn(SessionParams(session_id=created.id), turns)
    finished = await finish_turn(SessionParams(session_id=created.id), turns)

    assert prepared.session_id == created.id
    assert finished.session_id == created.id
    assert [event for event, _ in runner.lifecycle] == ["prepare", "finish"]


async def test_start_turn_runs_the_agent_in_the_background(
    session_repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    publisher = _RecordingPublisher()
    sessions, turns = _services(
        session_repository, session_factory, _LifecycleAgentRunner(), publisher
    )
    created = await create_session(CreateSessionParams(channel=_CHANNEL), sessions)

    result = await start_turn(
        StartTurnParams(session_id=created.id, message="hello"), turns
    )
    await _wait_for_turn_completed(publisher)

    assert result.session_id == created.id
    snapshot = await get_session(SessionParams(session_id=created.id), sessions)
    reply = snapshot.items[-1]
    assert isinstance(reply, AssistantMessageItem)
    assert reply.content == "done"


async def test_cancel_turn_releases_the_session_for_a_new_turn(
    session_repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    runner = _HangingAgentRunner()
    sessions, turns = _services(session_repository, session_factory, runner)
    created = await create_session(CreateSessionParams(channel=_CHANNEL), sessions)
    await start_turn(StartTurnParams(session_id=created.id, message="hello"), turns)
    await asyncio.wait_for(runner.started.wait(), timeout=1)

    await cancel_turn(SessionParams(session_id=created.id), turns)
    result = await start_turn(
        StartTurnParams(session_id=created.id, message="hello again"), turns
    )

    assert result.session_id == created.id


async def test_turn_methods_raise_for_an_unknown_session(
    session_repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, turns = _services(session_repository, session_factory, _LifecycleAgentRunner())

    with pytest.raises(SessionNotFoundError):
        await prepare_turn(SessionParams(session_id=uuid4()), turns)


async def _wait_for_turn_completed(
    publisher: _RecordingPublisher,
    timeout: float = 2.0,
) -> None:
    async with asyncio.timeout(timeout):
        while not any(
            event.type is ConversationEventType.TURN_COMPLETED
            for event in publisher.events
        ):
            await asyncio.sleep(0.01)
