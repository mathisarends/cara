import asyncio
from collections.abc import AsyncIterator

import pytest

from gateway.features.conversation.application import (
    AgentChannelRef,
    AgentEvent,
    AgentRunRequest,
    AgentRuntime,
    AgentSessionRef,
    ChatCompleted,
    ChatDelta,
    ConversationEvent,
    ConversationEventType,
    ConversationTurnFailed,
    ConversationTurnSteered,
    EventPublisher,
    SessionService,
    ToolCallCompleted,
    ToolCallStarted,
    TurnLease,
    TurnSteered,
    TurnWorker,
)
from gateway.features.conversation.domain import (
    ChannelRef,
    NoActiveTurnError,
    SessionRepository,
    ToolCallSequence,
    ToolCallState,
    UserMessage,
)
from gateway.shared import UnitOfWork

_CHANNEL = ChannelRef("test")


class _FailingAgentRuntime(AgentRuntime):
    async def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        del request
        raise NotImplementedError
        yield

    async def close(self) -> None:
        pass

    async def prepare(self, session: AgentSessionRef) -> None:
        pass

    async def steer(self, session: AgentSessionRef, text: str) -> None:
        raise NotImplementedError("This test runtime does not support steering")

    async def finish(self, session: AgentSessionRef) -> None:
        pass


class _StreamingAgentRuntime(AgentRuntime):
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

    async def steer(self, session: AgentSessionRef, text: str) -> None:
        raise NotImplementedError("This test runtime does not support steering")


class _BlockingFirstAgentRuntime(AgentRuntime):
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

    async def prepare(self, session: AgentSessionRef) -> None:
        pass

    async def steer(self, session: AgentSessionRef, text: str) -> None:
        raise NotImplementedError("This test runtime does not support steering")

    async def finish(self, session: AgentSessionRef) -> None:
        pass


class _SteerableAgentRuntime(AgentRuntime):
    def __init__(self) -> None:
        self.tool_started = asyncio.Event()
        self._steering: asyncio.Queue[str] = asyncio.Queue()

    async def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        del request
        yield ToolCallStarted("call-1", "lookup", {"query": "Cara"})
        self.tool_started.set()
        steered = await self._steering.get()
        yield ToolCallCompleted("call-1", "lookup", {"answer": 42})
        yield TurnSteered(steered)
        yield ChatCompleted("Hello", finish_reason="stop")

    async def steer(self, session: AgentSessionRef, text: str) -> None:
        del session
        await self._steering.put(text)

    async def close(self) -> None:
        pass

    async def prepare(self, session: AgentSessionRef) -> None:
        pass

    async def finish(self, session: AgentSessionRef) -> None:
        pass


class _RecordingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.events: list[ConversationEvent] = []
        self._published = asyncio.Condition()

    async def publish(self, event: ConversationEvent) -> None:
        async with self._published:
            self.events.append(event)
            self._published.notify_all()

    async def wait_for(self, event_type: ConversationEventType) -> None:
        async with asyncio.timeout(2), self._published:
            await self._published.wait_for(
                lambda: any(event.type is event_type for event in self.events)
            )


@pytest.fixture
def publisher() -> _RecordingPublisher:
    return _RecordingPublisher()


async def test_prepare_and_finish_forward_the_session_to_the_agent(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
    publisher: _RecordingPublisher,
) -> None:
    runner = _StreamingAgentRuntime()
    sessions, turns = _services(session_units, lease_units, publisher, runner)
    session = await sessions.create(channel=ChannelRef("voice"))

    await turns.prepare(session.id)
    await turns.finish(session.id)

    assert runner.prepared == [AgentSessionRef(session.id, AgentChannelRef("voice"))]
    assert runner.finished == runner.prepared


async def test_failed_turn_publishes_turn_failed_event(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
    publisher: _RecordingPublisher,
) -> None:
    sessions, turns = _services(
        session_units,
        lease_units,
        publisher,
        _FailingAgentRuntime(),
    )
    session = await sessions.create(channel=_CHANNEL)

    await turns.start(session_id=session.id, text="hello")
    await publisher.wait_for(ConversationEventType.TURN_FAILED)
    await turns.close()

    assert [event.type for event in publisher.events] == [
        ConversationEventType.TURN_STARTED,
        ConversationEventType.TURN_FAILED,
    ]
    failure = publisher.events[1]
    assert isinstance(failure, ConversationTurnFailed)
    assert failure.session_id == session.id
    # NotImplementedError carries no message, so the type name stands in for it.
    assert failure.code == "NotImplementedError"
    assert failure.message == "NotImplementedError"


async def test_agent_stream_updates_session_and_publishes_ordered_events(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
    publisher: _RecordingPublisher,
) -> None:
    runner = _StreamingAgentRuntime()
    sessions, turns = _services(session_units, lease_units, publisher, runner)
    session = await sessions.create(channel=_CHANNEL)

    await turns.start(session_id=session.id, text="hello")
    await publisher.wait_for(ConversationEventType.TURN_COMPLETED)

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


async def test_steering_reaches_the_running_agent_and_lands_in_the_transcript(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
    publisher: _RecordingPublisher,
) -> None:
    runner = _SteerableAgentRuntime()
    sessions, turns = _services(session_units, lease_units, publisher, runner)
    session = await sessions.create(channel=_CHANNEL)
    await turns.start(session_id=session.id, text="hello")
    await asyncio.wait_for(runner.tool_started.wait(), timeout=1)

    await turns.steer(session_id=session.id, text="also check Hamburg")
    await publisher.wait_for(ConversationEventType.TURN_COMPLETED)

    assert [event.type for event in publisher.events] == [
        ConversationEventType.TURN_STARTED,
        ConversationEventType.TOOL_CALL_STARTED,
        ConversationEventType.TOOL_CALL_COMPLETED,
        ConversationEventType.TURN_STEERED,
        ConversationEventType.CHAT_COMPLETED,
        ConversationEventType.TURN_COMPLETED,
    ]
    steered = publisher.events[3]
    assert isinstance(steered, ConversationTurnSteered)
    assert steered.text == "also check Hamburg"

    persisted = await sessions.get(session.id)
    assert [type(entry).__name__ for entry in persisted.entries] == [
        "UserMessage",
        "ToolCallSequence",
        "UserMessage",
        "AssistantMessage",
    ]
    assert [
        entry.content for entry in persisted.entries if isinstance(entry, UserMessage)
    ] == ["hello", "also check Hamburg"]
    await turns.close()


async def test_steering_without_an_active_turn_is_rejected(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
    publisher: _RecordingPublisher,
) -> None:
    sessions, turns = _services(
        session_units,
        lease_units,
        publisher,
        _SteerableAgentRuntime(),
    )
    session = await sessions.create(channel=_CHANNEL)

    with pytest.raises(NoActiveTurnError):
        await turns.steer(session_id=session.id, text="anybody there?")


async def test_automation_turn_uses_full_context_without_a_synthetic_user_message(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
    publisher: _RecordingPublisher,
) -> None:
    runner = _StreamingAgentRuntime()
    sessions, turns = _services(session_units, lease_units, publisher, runner)
    session = await sessions.create(channel=_CHANNEL)

    await turns.start_scheduled(
        session_id=session.id,
        text="[Scheduled agent run] Play bird sounds and wake the user",
    )

    request = runner.requests[0]
    persisted = await sessions.get(session.id)
    assert request.input_id is None
    assert request.input == "[Scheduled agent run] Play bird sounds and wake the user"
    assert [type(entry).__name__ for entry in persisted.entries] == [
        "ToolCallSequence",
        "AssistantMessage",
    ]
    await turns.close()


async def test_automation_turn_waits_for_an_active_interactive_turn(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
    publisher: _RecordingPublisher,
) -> None:
    runner = _BlockingFirstAgentRuntime()
    sessions, turns = _services(session_units, lease_units, publisher, runner)
    session = await sessions.create(channel=_CHANNEL)
    await turns.start(session_id=session.id, text="Schedule this")
    await asyncio.wait_for(runner.first_started.wait(), timeout=1)

    automation = asyncio.create_task(
        turns.start_scheduled(
            session_id=session.id,
            text="[Scheduled agent run] Execute this",
        )
    )
    # Observe the real 250 ms lease retry while the interactive turn stays active.
    await asyncio.sleep(0.3)
    assert not automation.done()

    runner.release_first.set()
    await asyncio.wait_for(automation, timeout=2)

    assert len(runner.requests) == 2
    assert runner.requests[1].input_id is None
    await turns.close()


class _Sessions:
    def __init__(self, units: UnitOfWork[SessionRepository]) -> None:
        self._units = units

    async def create(self, *, channel: ChannelRef):
        async with self._units() as repository:
            return await SessionService(repository).create(channel=channel)

    async def get(self, session_id):
        async with self._units() as repository:
            return await SessionService(repository).get(session_id)


def _services(
    session_units: UnitOfWork[SessionRepository],
    lease_units: UnitOfWork[TurnLease],
    publisher: EventPublisher,
    runner: AgentRuntime,
) -> tuple[_Sessions, TurnWorker]:
    sessions = _Sessions(session_units)
    turns = TurnWorker(session_units, lease_units, publisher, runner)
    return sessions, turns
