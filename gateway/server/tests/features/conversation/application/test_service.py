import asyncio
from collections.abc import AsyncIterator

import pytest

from agent_plugin_api import (
    AgentEvent,
    AgentRunner,
    AgentRunRequest,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
)
from gateway.features.conversation.application.ports import EventPublisher
from gateway.features.conversation.application.service import ConversationService
from gateway.features.conversation.domain import (
    ChannelRef,
    GatewayEvent,
    GatewayEventType,
    ToolCallSequence,
    ToolCallState,
)
from gateway.features.conversation.infrastructure.persistence import (
    SQLSessionRepository,
)

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

    async def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        self.requests.append(request)
        yield ChatDelta("Hel")
        yield ToolCallStarted("call-1", "lookup", {"query": "Cara"})
        yield ToolCallCompleted("call-1", "lookup", {"answer": 42})
        yield ChatCompleted("Hello", finish_reason="stop")

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
        self.events: list[GatewayEvent] = []

    async def publish(self, event: GatewayEvent) -> None:
        self.events.append(event)


@pytest.fixture
def publisher() -> _RecordingPublisher:
    return _RecordingPublisher()


async def test_failed_turn_publishes_turn_failed_event(
    session_repository: SQLSessionRepository,
    publisher: _RecordingPublisher,
) -> None:
    service = ConversationService(session_repository, publisher, _FailingAgentRunner())
    session = await service.create_session(_CHANNEL, {})

    await service.start_turn(session.id, "hello", {})
    await _wait_for_event(publisher, GatewayEventType.TURN_FAILED)
    await service.close()

    assert [event.type for event in publisher.events] == [
        GatewayEventType.TURN_STARTED,
        GatewayEventType.TURN_FAILED,
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
    publisher: _RecordingPublisher,
) -> None:
    runner = _StreamingAgentRunner()
    service = ConversationService(session_repository, publisher, runner)
    session = await service.create_session(_CHANNEL, {})

    await service.start_turn(session.id, "hello", {})
    await _wait_for_event(publisher, GatewayEventType.TURN_COMPLETED)

    assert [event.type for event in publisher.events] == [
        GatewayEventType.TURN_STARTED,
        GatewayEventType.CHAT_DELTA,
        GatewayEventType.TOOL_CALL_STARTED,
        GatewayEventType.TOOL_CALL_COMPLETED,
        GatewayEventType.CHAT_COMPLETED,
        GatewayEventType.TURN_COMPLETED,
    ]
    assert [event.sequence for event in publisher.events] == list(range(1, 7))

    persisted = await service.get_session(session.id)
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

    await service.close()


async def test_automation_turn_uses_full_context_without_a_synthetic_user_message(
    session_repository: SQLSessionRepository,
    publisher: _RecordingPublisher,
) -> None:
    runner = _StreamingAgentRunner()
    service = ConversationService(session_repository, publisher, runner)
    session = await service.create_session(_CHANNEL, {})

    await service.run_automation_turn(
        session.id,
        "[Scheduled agent run] Play bird sounds and wake the user",
        {"origin": "automation", "automation_kind": "reminder"},
    )

    request = runner.requests[0]
    persisted = await service.get_session(session.id)
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
    await service.close()


async def test_automation_turn_waits_for_an_active_interactive_turn(
    session_repository: SQLSessionRepository,
    publisher: _RecordingPublisher,
) -> None:
    runner = _BlockingFirstAgentRunner()
    service = ConversationService(session_repository, publisher, runner)
    session = await service.create_session(_CHANNEL, {})
    await service.start_turn(session.id, "Schedule this", {})
    await asyncio.wait_for(runner.first_started.wait(), timeout=1)

    automation = asyncio.create_task(
        service.run_automation_turn(
            session.id,
            "[Scheduled agent run] Execute this",
            {"origin": "automation"},
        )
    )
    await asyncio.sleep(0.3)
    assert not automation.done()

    runner.release_first.set()
    await asyncio.wait_for(automation, timeout=2)

    assert len(runner.requests) == 2
    assert runner.requests[1].input_id is None
    assert runner.requests[1].turn_metadata == {"origin": "automation"}
    await service.close()


async def _wait_for_event(
    publisher: _RecordingPublisher,
    event_type: GatewayEventType,
    timeout: float = 5.0,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while (
        not any(event.type is event_type for event in publisher.events)
        and loop.time() < deadline
    ):
        await asyncio.sleep(0.01)
