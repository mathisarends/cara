import pytest

from gateway.features.conversation.domain import (
    AssistantMessage,
    ChannelRef,
    NoPendingToolCallSequenceError,
    PendingToolCallsError,
    Session,
    ToolCallSequence,
    ToolCallState,
    UserMessage,
)

_CHANNEL = ChannelRef("test")


def test_session_owns_an_ordered_conversation() -> None:
    session = Session.create(_CHANNEL)

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

    assert session.channel == _CHANNEL
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
    entries = [UserMessage("Hello")]
    session = Session(channel=_CHANNEL, entries=entries)

    entries.append(AssistantMessage("Changed outside"))

    assert len(session.entries) == 1


def test_session_rejects_messages_while_tool_calls_are_pending() -> None:
    session = Session.create(_CHANNEL)
    session.add_user_message("Search for this")
    session.add_tool_call("call-1", "search", {"query": "Cara"})

    with pytest.raises(PendingToolCallsError):
        session.add_user_message("Are you done?")

    with pytest.raises(PendingToolCallsError):
        session.add_assistant_message("Not yet")


def test_session_rejects_tool_results_without_pending_sequence() -> None:
    session = Session.create(_CHANNEL)

    with pytest.raises(NoPendingToolCallSequenceError):
        session.resolve_tool_call("call-1", "result")


def test_session_can_fail_a_pending_tool_call_directly() -> None:
    session = Session.create(_CHANNEL)
    session.add_user_message("Search for this")
    call = session.add_tool_call("call-1", "search", {"query": "Cara"})

    failed = session.fail_tool_call("call-1", "timeout")

    assert failed is call
    assert failed.state is ToolCallState.FAILED
    assert failed.error == "timeout"


def test_pending_tool_call_sequence_exposes_the_open_sequence() -> None:
    session = Session.create(_CHANNEL)

    assert session.pending_tool_call_sequence() is None

    session.add_user_message("Search for this")
    session.add_tool_call("call-1", "search", {"query": "Cara"})

    sequence = session.pending_tool_call_sequence()
    assert isinstance(sequence, ToolCallSequence)
    assert sequence.calls[0].call_id == "call-1"


def test_failing_pending_tool_calls_resolves_every_open_call() -> None:
    session = Session.create(_CHANNEL)
    session.add_user_message("Search for this")
    session.add_tool_call("call-1", "search", {"query": "Cara"})
    session.add_tool_call("call-2", "weather", {"city": "Hamburg"})
    session.resolve_tool_call("call-1", {"result": "ok"})

    failed = session.fail_pending_tool_calls("cancelled")

    assert [call.call_id for call in failed] == ["call-2"]
    assert failed[0].state is ToolCallState.FAILED
    assert failed[0].error == "cancelled"


def test_failing_pending_tool_calls_without_a_pending_sequence_is_a_noop() -> None:
    session = Session.create(_CHANNEL)

    assert session.fail_pending_tool_calls("cancelled") == ()
