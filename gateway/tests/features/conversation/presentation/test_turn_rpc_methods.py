import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from gateway.features.conversation.application import (
    AgentEvent,
    AgentRunRequest,
    AgentRuntime,
    AgentSessionRef,
    ChatCompleted,
    ConversationEvent,
    ConversationEventType,
    EventPublisher,
    SessionService,
    TurnLease,
    TurnService,
    TurnWorker,
)
from gateway.features.conversation.domain import (
    AssistantMessage,
    ChannelRef,
    SessionNotFoundError,
    SessionRepository,
    SortOrder,
)
from gateway.features.conversation.presentation.rpc.methods import (
    cancel_turn,
    finish_turn,
    prepare_turn,
    start_turn,
)
from gateway.features.conversation.presentation.rpc.models import (
    SessionParams,
    StartTurnParams,
)
from gateway.shared import Transaction, UnitOfWork

_CHANNEL = ChannelRef("voice")


class _RecordingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.events: list[ConversationEvent] = []

    async def publish(self, event: ConversationEvent) -> None:
        self.events.append(event)


class _LifecycleAgentRuntime(AgentRuntime):
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


class _HangingAgentRuntime(AgentRuntime):
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
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
    runner: AgentRuntime,
    publisher: EventPublisher | None = None,
) -> tuple[SessionService, TurnService]:
    repository = _Repository(session_units)
    sessions = SessionService(repository)
    worker = TurnWorker(
        session_units,
        lease_units,
        publisher or _RecordingPublisher(),
        runner,
    )
    turns = TurnService(
        repository,
        _Lease(lease_units),
        _ImmediateTransaction(),
        worker,
    )
    return sessions, turns


class _Repository(SessionRepository):
    def __init__(self, units: UnitOfWork[SessionRepository]) -> None:
        self._units = units

    async def find_by_id(self, id):
        async with self._units() as repository:
            return await repository.find_by_id(id)

    async def find_latest_by_channel(self, channel):
        async with self._units() as repository:
            return await repository.find_latest_by_channel(channel)

    async def find_many(self, *, limit: int, order: SortOrder):
        async with self._units() as repository:
            return await repository.find_many(limit=limit, order=order)

    async def save(self, domain):
        async with self._units() as repository:
            return await repository.save(domain)


class _Lease(TurnLease):
    def __init__(self, units: UnitOfWork[TurnLease]) -> None:
        self._units = units

    async def acquire(self, session_id):
        async with self._units() as lease:
            return await lease.acquire(session_id)

    async def release(self, session_id):
        async with self._units() as lease:
            await lease.release(session_id)


class _ImmediateTransaction(Transaction):
    def after_commit(self, action) -> None:
        action()


async def test_prepare_and_finish_turn_forward_the_session(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
) -> None:
    runner = _LifecycleAgentRuntime()
    sessions, turns = _services(session_units, lease_units, runner)
    created = await sessions.create(channel=_CHANNEL)

    prepared = await prepare_turn(SessionParams(session_id=created.id), turns)
    finished = await finish_turn(SessionParams(session_id=created.id), turns)

    assert prepared.session_id == created.id
    assert finished.session_id == created.id
    assert [event for event, _ in runner.lifecycle] == ["prepare", "finish"]


async def test_start_turn_runs_the_agent_in_the_background(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
) -> None:
    publisher = _RecordingPublisher()
    sessions, turns = _services(
        session_units, lease_units, _LifecycleAgentRuntime(), publisher
    )
    created = await sessions.create(channel=_CHANNEL)

    result = await start_turn(
        StartTurnParams(session_id=created.id, message="hello"), turns
    )
    await _wait_for_turn_completed(publisher)

    assert result.session_id == created.id
    session = await sessions.get(created.id)
    reply = session.entries[-1]
    assert isinstance(reply, AssistantMessage)
    assert reply.content == "done"


async def test_cancel_turn_releases_the_session_for_a_new_turn(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
) -> None:
    runner = _HangingAgentRuntime()
    sessions, turns = _services(session_units, lease_units, runner)
    created = await sessions.create(channel=_CHANNEL)
    await start_turn(StartTurnParams(session_id=created.id, message="hello"), turns)
    await asyncio.wait_for(runner.started.wait(), timeout=1)

    await cancel_turn(SessionParams(session_id=created.id), turns)
    result = await start_turn(
        StartTurnParams(session_id=created.id, message="hello again"), turns
    )

    assert result.session_id == created.id
    await turns.cancel(created.id)


async def test_turn_methods_raise_for_an_unknown_session(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
) -> None:
    _, turns = _services(session_units, lease_units, _LifecycleAgentRuntime())

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
