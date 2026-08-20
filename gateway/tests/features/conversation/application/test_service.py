import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

import pytest

from gateway.features.conversation.application import (
    AgentEvent,
    AgentRunner,
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
        session_id: UUID,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentEvent]:
        del session_id, metadata
        raise NotImplementedError
        yield


class _StreamingAgentRunner(AgentRunner):
    async def run(
        self,
        session_id: UUID,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentEvent]:
        del session_id, metadata
        yield ChatDelta("Hel")
        yield ToolCallStarted("call-1", "lookup", {"query": "Cara"})
        yield ToolCallCompleted("call-1", "lookup", {"answer": 42})
        yield ChatCompleted("Hello", finish_reason="stop")


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
    service = ConversationService(
        session_repository, publisher, _StreamingAgentRunner()
    )
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
