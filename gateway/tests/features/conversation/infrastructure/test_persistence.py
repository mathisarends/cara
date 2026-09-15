from gateway.features.conversation.domain import (
    AssistantMessage,
    ChannelRef,
    Session,
    ToolCallSequence,
    ToolCallState,
    UserMessage,
)
from gateway.features.conversation.infrastructure.repository import (
    SQLSessionRepository,
)

_CHANNEL = ChannelRef("web", account_id="local")


async def test_session_aggregate_round_trips_with_complete_history(
    session_repository: SQLSessionRepository,
) -> None:
    session = Session.create(_CHANNEL)
    user_message = session.add_user_message("Weather in Hamburg")
    tool_call = session.add_tool_call("call-1", "weather", {"city": "Hamburg"})
    session.resolve_tool_call("call-1", {"temperature": 21})
    assistant_message = session.add_assistant_message("It is 21 degrees.")

    await session_repository.save(session)
    restored = await session_repository.find_by_id(session.id)

    assert restored is not None
    assert restored.id == session.id
    assert restored.channel == _CHANNEL
    assert [type(entry) for entry in restored.entries] == [
        UserMessage,
        ToolCallSequence,
        AssistantMessage,
    ]
    restored_user, restored_sequence, restored_assistant = restored.entries
    assert restored_user.id == user_message.id
    assert restored_assistant.id == assistant_message.id
    assert isinstance(restored_sequence, ToolCallSequence)
    assert restored_sequence.calls[0].id == tool_call.id
    assert restored_sequence.calls[0].state is ToolCallState.COMPLETED
    assert restored_sequence.calls[0].result == {"temperature": 21}


async def test_saving_updated_aggregate_replaces_removed_child_rows(
    session_repository: SQLSessionRepository,
) -> None:
    session = Session.create(_CHANNEL)
    session.add_user_message("First")
    await session_repository.save(session)

    session.add_assistant_message("Second")
    await session_repository.save(session)
    restored = await session_repository.find_by_id(session.id)

    assert restored is not None
    assert [entry.content for entry in restored.entries] == ["First", "Second"]


async def test_latest_session_can_be_found_by_its_complete_channel_identity(
    session_repository: SQLSessionRepository,
) -> None:
    other_account = ChannelRef("web", account_id="someone-else")
    first = await session_repository.save(Session.create(_CHANNEL))
    latest = await session_repository.save(Session.create(_CHANNEL))
    await session_repository.save(Session.create(other_account))

    restored = await session_repository.find_latest_by_channel(_CHANNEL)

    assert restored is not None
    assert restored.id == latest.id
    assert restored.id != first.id
