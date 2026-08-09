import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from gateway.features.conversation.domain import (
    AssistantMessage,
    Session,
    ToolCallSequence,
    ToolCallState,
    UserMessage,
)
from gateway.features.conversation.infrastructure.persistence import (
    SQLSessionRepository,
)


def test_session_aggregate_round_trips_with_complete_history() -> None:
    asyncio.run(_assert_session_aggregate_round_trip())


async def _assert_session_aggregate_round_trip() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    repository = SQLSessionRepository(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    session = Session.create(metadata={"channel": "web"})
    user_message = session.add_user_message("Weather in Hamburg")
    tool_call = session.add_tool_call(
        "call-1",
        "weather",
        {"city": "Hamburg"},
    )
    session.resolve_tool_call("call-1", {"temperature": 21})
    assistant_message = session.add_assistant_message("It is 21 degrees.")

    await repository.save(session)
    restored = await repository.find_by_id(session.id)

    assert restored is not None
    assert restored.id == session.id
    assert restored.metadata == {"channel": "web"}
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

    await engine.dispose()


def test_saving_updated_aggregate_replaces_removed_child_rows() -> None:
    asyncio.run(_assert_saving_updated_aggregate())


async def _assert_saving_updated_aggregate() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    repository = SQLSessionRepository(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    session = Session.create()
    session.add_user_message("First")
    await repository.save(session)

    session.add_assistant_message("Second")
    await repository.save(session)
    restored = await repository.find_by_id(session.id)

    assert restored is not None
    assert [entry.content for entry in restored.entries] == ["First", "Second"]

    await engine.dispose()
