import pytest

from gateway.features.conversation.domain import (
    ToolCall,
    ToolCallAlreadyResolvedError,
    ToolCallState,
)


def test_new_tool_call_starts_pending() -> None:
    call = ToolCall("call-1", "weather", {"city": "Hamburg"})

    assert call.state is ToolCallState.PENDING
    assert call.is_pending
    assert call.result is None
    assert call.error is None


def test_completing_a_pending_call_stores_its_result() -> None:
    call = ToolCall("call-1", "weather", {"city": "Hamburg"})

    call.complete({"temperature": 21})

    assert call.state is ToolCallState.COMPLETED
    assert not call.is_pending
    assert call.result == {"temperature": 21}


def test_failing_a_pending_call_stores_its_error() -> None:
    call = ToolCall("call-1", "weather", {"city": "Hamburg"})

    call.fail("timeout")

    assert call.state is ToolCallState.FAILED
    assert not call.is_pending
    assert call.error == "timeout"


def test_completing_an_already_resolved_call_is_rejected() -> None:
    call = ToolCall("call-1", "weather", {})
    call.complete({"temperature": 21})

    with pytest.raises(ToolCallAlreadyResolvedError):
        call.complete({"temperature": 22})


def test_failing_an_already_resolved_call_is_rejected() -> None:
    call = ToolCall("call-1", "weather", {})
    call.fail("timeout")

    with pytest.raises(ToolCallAlreadyResolvedError):
        call.fail("timeout again")


def test_function_arguments_do_not_expose_the_internal_mapping() -> None:
    arguments = {"city": "Hamburg"}
    call = ToolCall("call-1", "weather", arguments)

    arguments["city"] = "Berlin"
    returned = call.function_arguments
    returned["city"] = "Munich"

    assert call.function_arguments == {"city": "Hamburg"}
