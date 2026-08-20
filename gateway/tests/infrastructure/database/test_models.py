from sqlalchemy.engine import Engine
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from gateway.infrastructure.database import (
    SessionAssistantMessageModel,
    SessionModel,
    SessionToolCallModel,
    SessionToolCallSequenceModel,
    SessionUserMessageModel,
)


def test_session_entries_and_tool_calls_are_ordered(sqlite_engine: Engine) -> None:
    model = SessionModel(
        user_messages=[
            SessionUserMessageModel(position=2, content="Second"),
            SessionUserMessageModel(position=0, content="First"),
        ],
        assistant_messages=[
            SessionAssistantMessageModel(position=3, content="Done"),
        ],
        tool_call_sequences=[
            SessionToolCallSequenceModel(
                position=1,
                calls=[
                    SessionToolCallModel(
                        position=1,
                        call_id="call-2",
                        function_name="weather",
                        function_arguments={"city": "Hamburg"},
                        state="completed",
                        result={"temperature": 21},
                    ),
                    SessionToolCallModel(
                        position=0,
                        call_id="call-1",
                        function_name="location",
                        function_arguments={},
                        state="completed",
                        result={"city": "Hamburg"},
                    ),
                ],
            ),
        ],
    )

    with Session(sqlite_engine) as database:
        database.add(model)
        database.commit()
        statement = select(SessionModel).options(
            selectinload(SessionModel.user_messages),
            selectinload(SessionModel.assistant_messages),
            selectinload(SessionModel.tool_call_sequences).selectinload(
                SessionToolCallSequenceModel.calls
            ),
        )
        restored = database.exec(statement).one()

        assert [message.position for message in restored.user_messages] == [0, 2]
        assert [call.call_id for call in restored.tool_call_sequences[0].calls] == [
            "call-1",
            "call-2",
        ]
        assert restored.tool_call_sequences[0].calls[1].result == {"temperature": 21}


def test_deleting_session_cascades_to_its_context_entries(
    sqlite_engine: Engine,
) -> None:
    model = SessionModel(
        user_messages=[SessionUserMessageModel(position=0, content="Hello")],
        tool_call_sequences=[
            SessionToolCallSequenceModel(
                position=1,
                calls=[
                    SessionToolCallModel(
                        position=0,
                        call_id="call-1",
                        function_name="search",
                        function_arguments={"query": "Cara"},
                        state="pending",
                    )
                ],
            )
        ],
    )

    with Session(sqlite_engine) as database:
        database.add(model)
        database.commit()
        database.delete(model)
        database.commit()

        assert database.exec(select(SessionUserMessageModel)).all() == []
        assert database.exec(select(SessionToolCallSequenceModel)).all() == []
        assert database.exec(select(SessionToolCallModel)).all() == []
