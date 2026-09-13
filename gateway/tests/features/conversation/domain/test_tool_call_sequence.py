import pytest

from gateway.features.conversation.domain import (
    DuplicateToolCallError,
    ToolCall,
    ToolCallNotFoundError,
    ToolCallSequence,
)


def test_new_sequence_is_incomplete_while_a_call_is_pending() -> None:
    sequence = ToolCallSequence(calls=[ToolCall("call-1", "weather", {})])

    assert not sequence.is_complete


def test_sequence_is_complete_once_every_call_is_resolved() -> None:
    sequence = ToolCallSequence(calls=[ToolCall("call-1", "weather", {})])

    sequence.resolve("call-1", {"temperature": 21})

    assert sequence.is_complete


def test_constructing_a_sequence_rejects_duplicate_call_ids() -> None:
    with pytest.raises(DuplicateToolCallError):
        ToolCallSequence(
            calls=[
                ToolCall("call-1", "weather", {}),
                ToolCall("call-1", "location", {}),
            ]
        )


def test_adding_a_duplicate_call_id_is_rejected() -> None:
    sequence = ToolCallSequence(calls=[ToolCall("call-1", "weather", {})])

    with pytest.raises(DuplicateToolCallError):
        sequence.add(ToolCall("call-1", "location", {}))


def test_resolving_an_unknown_call_id_is_rejected() -> None:
    sequence = ToolCallSequence(calls=[ToolCall("call-1", "weather", {})])

    with pytest.raises(ToolCallNotFoundError):
        sequence.resolve("call-2", "result")


def test_failing_an_unknown_call_id_is_rejected() -> None:
    sequence = ToolCallSequence(calls=[ToolCall("call-1", "weather", {})])

    with pytest.raises(ToolCallNotFoundError):
        sequence.fail("call-2", "error")
