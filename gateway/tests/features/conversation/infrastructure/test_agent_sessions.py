from uuid import uuid4

import pytest

from agent_plugin_api import (
    AgentAssistantMessage,
    AgentToolCallSequence,
    AgentToolCallState,
    AgentUserMessage,
)
from gateway.features.conversation.domain import ChannelRef, Session
from gateway.features.conversation.infrastructure import GatewayAgentSessionReader
from gateway.features.conversation.infrastructure.persistence import (
    SQLSessionRepository,
)


async def test_reader_returns_only_context_before_the_current_input(
    session_repository: SQLSessionRepository,
) -> None:
    session = Session.create(ChannelRef("voice", "local"), {"locale": "de"})
    first_input = session.add_user_message("First")
    session.add_assistant_message("Answer")
    current_input = session.add_user_message("Current")
    await session_repository.save(session)
    reader = GatewayAgentSessionReader(session_repository)

    context = await reader.context_for_turn(session.id, current_input.id)

    assert context.session_metadata == {"locale": "de"}
    assert context.entries == (
        AgentUserMessage(first_input.id, "First"),
        AgentAssistantMessage(session.entries[1].id, "Answer"),
    )


async def test_reader_preserves_completed_tool_call_rounds(
    session_repository: SQLSessionRepository,
) -> None:
    session = Session.create(ChannelRef("voice"))
    session.add_user_message("Look it up")
    call = session.add_tool_call("call-1", "search", {"query": "Cara"})
    session.resolve_tool_call("call-1", {"result": "ok"})
    current_input = session.add_user_message("Continue")
    await session_repository.save(session)
    reader = GatewayAgentSessionReader(session_repository)

    context = await reader.context_for_turn(session.id, current_input.id)

    sequence = context.entries[1]
    assert isinstance(sequence, AgentToolCallSequence)
    assert sequence.calls[0].id == call.id
    assert sequence.calls[0].state is AgentToolCallState.COMPLETED
    assert sequence.calls[0].result == {"result": "ok"}


async def test_reader_rejects_an_input_from_another_session(
    session_repository: SQLSessionRepository,
) -> None:
    session = await session_repository.save(Session.create(ChannelRef("voice")))
    reader = GatewayAgentSessionReader(session_repository)

    with pytest.raises(ValueError, match="does not belong"):
        await reader.context_for_turn(session.id, uuid4())


async def test_reader_returns_full_context_for_a_server_initiated_turn(
    session_repository: SQLSessionRepository,
) -> None:
    session = Session.create(ChannelRef("voice"), {"locale": "de"})
    input_message = session.add_user_message("Wake me in twenty minutes")
    session.add_assistant_message("Okay")
    await session_repository.save(session)
    reader = GatewayAgentSessionReader(session_repository)

    context = await reader.context_for_turn(session.id, None)

    assert context.entries == (
        AgentUserMessage(input_message.id, "Wake me in twenty minutes"),
        AgentAssistantMessage(session.entries[1].id, "Okay"),
    )
