import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_plugin_api import (
    AgentChannelRef,
    AgentEvent,
    AgentRunner,
    AgentRunRequest,
    AgentSessionRef,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
)
from gateway.features.conversation.application import (
    ConversationEvent,
    ConversationEventType,
    EventPublisher,
    SessionService,
    TurnService,
)
from gateway.features.conversation.domain import (
    ChannelRef,
    ToolCallSequence,
    ToolCallState,
)
from gateway.features.conversation.infrastructure.persistence import (
    SQLSessionRepository,
)
from gateway.features.conversation.infrastructure.turn_lease import SQLTurnLease

_CHANNEL = ChannelRef("test")


class _FailingAgentRunner(AgentRunner):
    async def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        del request
        raise NotImplementedError
        yield

    async def close(self) -> None:
        pass


class _StreamingAgentRunner(AgentRunner):
    def __init__(self) -> None:
        self.requests: list[AgentRunRequest] = []
        self.prepared: list[AgentSessionRef] = []
        self.finished: list[AgentSessionRef] = []

    async def prepare(self, session: AgentSessionRef) -> None:
        self.prepared.append(session)

    async def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        self.requests.append(request)
        yield ChatDelta("Hel")
        yield ToolCallStarted("call-1", "lookup", {"query": "Cara"})
        yield ToolCallCompleted("call-1", "lookup", {"answer": 42})
        yield ChatCompleted("Hello", finish_reason="stop")

    async def finish(self, session: AgentSessionRef) -> None:
        self.finished.append(session)

    async def close(self) -> None:
        pass


class _BlockingFirstAgentRunner(AgentRunner):
    def __init__(self) -> None:
        self.requests: list[AgentRunRequest] = []
        self.first_started = asyncio.Event()
        self.release_first = asyncio.Event()

    async def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        self.requests.append(request)
        if len(self.requests) == 1:
            self.first_started.set()
            await self.release_first.wait()
        yield ChatCompleted("Done", finish_reason="stop")

    async def close(self) -> None:
        pass


class _RecordingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.events: list[ConversationEvent] = []

    async def publish(self, event: ConversationEvent) -> None:
        self.events.append(event)


@pytest.fixture
def publisher() -> _RecordingPublisher:
    return _RecordingPublisher()


async def test_prepare_and_finish_forward_the_session_to_the_agent(
    session_repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: _RecordingPublisher,
) -> None:
    runner = _StreamingAgentRunner()
    sessions, turns = _services(session_repository, session_factory, publisher, runner)
    session = await sessions.create(
        channel=ChannelRef("voice", "kitchen"),
        metadata={},
    )

    await turns.prepare(session.id)
    await turns.finish(session.id)

    assert runner.prepared == [
        AgentSessionRef(session.id, AgentChannelRef("voice", "kitchen"))
    ]
    assert runner.finished == runner.prepared


async def test_failed_turn_publishes_turn_failed_event(
    session_repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: _RecordingPublisher,
) -> None:
    sessions, turns = _services(
        session_repository,
        session_factory,
        publisher,
        _FailingAgentRunner(),
    )
    session = await sessions.create(channel=_CHANNEL, metadata={})

    await turns.start(session_id=session.id, text="hello", metadata={})
    await _wait_for_event(publisher, ConversationEventType.TURN_FAILED)
    await turns.close()

    assert [event.type for event in publisher.events] == [
        ConversationEventType.TURN_STARTED,
        ConversationEventType.TURN_FAILED,
    ]
    failure = publisher.events[1]
    assert failure.session_id == session.id
    # NotImplementedError carries no message, so the type name stands in for it.
    assert failure.data == {
        "code": "NotImplementedError",
        "message": "NotImplementedError",
    }


async def test_agent_stream_updates_session_and_publishes_ordered_events(
    session_repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: _RecordingPublisher,
) -> None:
    runner = _StreamingAgentRunner()
    sessions, turns = _services(session_repository, session_factory, publisher, runner)
    session = await sessions.create(channel=_CHANNEL, metadata={})

    await turns.start(session_id=session.id, text="hello", metadata={})
    await _wait_for_event(publisher, ConversationEventType.TURN_COMPLETED)

    assert [event.type for event in publisher.events] == [
        ConversationEventType.TURN_STARTED,
        ConversationEventType.CHAT_DELTA,
        ConversationEventType.TOOL_CALL_STARTED,
        ConversationEventType.TOOL_CALL_COMPLETED,
        ConversationEventType.CHAT_COMPLETED,
        ConversationEventType.TURN_COMPLETED,
    ]
    assert [event.sequence for event in publisher.events] == list(range(1, 7))

    persisted = await sessions.get(session.id)
    request = runner.requests[0]
    assert request.session.id == session.id
    assert request.session.channel.name == "test"
    assert request.input == "hello"
    assert request.input_id == persisted.entries[0].id
    assert request.turn_id != request.input_id
    assert [type(entry).__name__ for entry in persisted.entries] == [
        "UserMessage",
        "ToolCallSequence",
        "AssistantMessage",
    ]
    sequence = persisted.entries[1]
    assert isinstance(sequence, ToolCallSequence)
    assert sequence.calls[0].state is ToolCallState.COMPLETED
    assert sequence.calls[0].result == {"answer": 42}

    await turns.close()


async def test_automation_turn_uses_full_context_without_a_synthetic_user_message(
    session_repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: _RecordingPublisher,
) -> None:
    runner = _StreamingAgentRunner()
    sessions, turns = _services(session_repository, session_factory, publisher, runner)
    session = await sessions.create(channel=_CHANNEL, metadata={})

    await turns.start_scheduled(
        session_id=session.id,
        text="[Scheduled agent run] Play bird sounds and wake the user",
        metadata={"origin": "automation", "automation_kind": "reminder"},
    )

    request = runner.requests[0]
    persisted = await sessions.get(session.id)
    assert request.input_id is None
    assert request.input == "[Scheduled agent run] Play bird sounds and wake the user"
    assert request.turn_metadata == {
        "origin": "automation",
        "automation_kind": "reminder",
    }
    assert [type(entry).__name__ for entry in persisted.entries] == [
        "ToolCallSequence",
        "AssistantMessage",
    ]
    await turns.close()


async def test_automation_turn_waits_for_an_active_interactive_turn(
    session_repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: _RecordingPublisher,
) -> None:
    runner = _BlockingFirstAgentRunner()
    sessions, turns = _services(session_repository, session_factory, publisher, runner)
    session = await sessions.create(channel=_CHANNEL, metadata={})
    await turns.start(session_id=session.id, text="Schedule this", metadata={})
    await asyncio.wait_for(runner.first_started.wait(), timeout=1)

    automation = asyncio.create_task(
        turns.start_scheduled(
            session_id=session.id,
            text="[Scheduled agent run] Execute this",
            metadata={"origin": "automation"},
        )
    )
    await asyncio.sleep(0.3)
    assert not automation.done()

    runner.release_first.set()
    await asyncio.wait_for(automation, timeout=2)

    assert len(runner.requests) == 2
    assert runner.requests[1].input_id is None
    assert runner.requests[1].turn_metadata == {"origin": "automation"}
    await turns.close()


async def _wait_for_event(
    publisher: _RecordingPublisher,
    event_type: ConversationEventType,
    timeout: float = 5.0,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while (
        not any(event.type is event_type for event in publisher.events)
        and loop.time() < deadline
    ):
        await asyncio.sleep(0.01)


def _services(
    repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: EventPublisher,
    runner: AgentRunner,
) -> tuple[SessionService, TurnService]:
    sessions = SessionService(repository)
    turns = TurnService(
        repository,
        sessions,
        SQLTurnLease(session_factory),
        publisher,
        runner,
    )
    return sessions, turns
