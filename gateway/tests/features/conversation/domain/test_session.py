import pytest

from gateway.features.conversation.domain import (
    AssistantMessage,
    NoPendingToolCallSequenceError,
    PendingToolCallsError,
    Session,
    ToolCallSequence,
    ToolCallState,
    UserMessage,
)


def test_session_owns_an_ordered_conversation() -> None:
    session = Session.create(metadata={"channel": "terminal"})

    user_message = session.add_user_message("How is the weather?")
    first_call = session.add_tool_call(
        "call-1",
        "location",
        {},
    )
    second_call = session.add_tool_call(
        "call-2",
        "weather",
        {"city": "Hamburg"},
    )
    session.resolve_tool_call("call-1", {"city": "Hamburg"})
    session.resolve_tool_call("call-2", {"temperature": 21})
    assistant_message = session.add_assistant_message("It is 21 degrees.")

    assert session.metadata == {"channel": "terminal"}
    assert [type(entry) for entry in session.entries] == [
        UserMessage,
        ToolCallSequence,
        AssistantMessage,
    ]
    assert session.entries[0] is user_message
    assert session.entries[2] is assistant_message
    sequence = session.entries[1]
    assert isinstance(sequence, ToolCallSequence)
    assert sequence.calls == (first_call, second_call)
    assert all(call.state is ToolCallState.COMPLETED for call in sequence.calls)


def test_session_does_not_expose_mutable_collections() -> None:
    metadata = {"channel": "terminal"}
    entries = [UserMessage("Hello")]
    session = Session(metadata=metadata, entries=entries)

    metadata["channel"] = "web"
    entries.append(AssistantMessage("Changed outside"))
    returned_metadata = session.metadata
    returned_metadata["channel"] = "voice"

    assert session.metadata == {"channel": "terminal"}
    assert len(session.entries) == 1


def test_session_rejects_messages_while_tool_calls_are_pending() -> None:
    session = Session.create()
    session.add_user_message("Search for this")
    session.add_tool_call("call-1", "search", {"query": "Cara"})

    with pytest.raises(PendingToolCallsError):
        session.add_user_message("Are you done?")

    with pytest.raises(PendingToolCallsError):
        session.add_assistant_message("Not yet")


def test_session_rejects_tool_results_without_pending_sequence() -> None:
    session = Session.create()

    with pytest.raises(NoPendingToolCallSequenceError):
        session.resolve_tool_call("call-1", "result")
