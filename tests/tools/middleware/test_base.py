import asyncio
import logging

from cara.tools import (
    ActionResult,
    ErrorBoundaryMiddleware,
    ResultLimitMiddleware,
    Tool,
    ToolCall,
    ToolContext,
    ToolFeedbackError,
    ToolHandler,
    ToolMiddleware,
    compose,
)
from cara.tools.middleware.call_log import CallLoggingMiddleware


async def _unused_tool() -> ActionResult:
    return ActionResult.success()


def _call() -> ToolCall:
    return ToolCall(
        tool=Tool(name="test", description=None, fn=_unused_tool),
        params=None,
        raw_args={},
        context=ToolContext(),
    )


class RecordingMiddleware(ToolMiddleware):
    def __init__(self, name: str, events: list[str]) -> None:
        self._name = name
        self._events = events

    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        self._events.append(f"{self._name}:request")
        result = await next(call)
        self._events.append(f"{self._name}:response")
        return result


def test_compose_uses_onion_order_for_request_and_response() -> None:
    events: list[str] = []

    async def terminal(call: ToolCall) -> ActionResult:
        del call
        events.append("tool")
        return ActionResult.success("done")

    handler = compose(
        [RecordingMiddleware("outer", events), RecordingMiddleware("inner", events)],
        terminal,
    )

    assert asyncio.run(handler(_call())) == ActionResult.success("done")
    assert events == ["outer:request", "inner:request", "tool", "inner:response", "outer:response"]


def test_error_boundary_returns_expected_feedback() -> None:
    async def terminal(call: ToolCall) -> ActionResult:
        del call
        raise ToolFeedbackError("Try another value.")

    result = asyncio.run(compose([ErrorBoundaryMiddleware()], terminal)(_call()))

    assert result == ActionResult.fail("Try another value.")


def test_error_boundary_hides_unexpected_error() -> None:
    async def terminal(call: ToolCall) -> ActionResult:
        del call
        raise RuntimeError("host details")

    result = asyncio.run(compose([ErrorBoundaryMiddleware()], terminal)(_call()))

    assert result == ActionResult.fail("Internal tool error.")


def test_result_limit_changes_successful_response_on_the_way_out() -> None:
    async def terminal(call: ToolCall) -> ActionResult:
        del call
        return ActionResult.success("x" * 100)

    result = asyncio.run(compose([ResultLimitMiddleware(max_chars=30)], terminal)(_call()))

    assert result.ok
    assert result.content is not None
    assert len(result.content) == 30
    assert result.content.endswith("[Output truncated.]")


def test_call_logging_records_arguments_and_result(caplog) -> None:
    call = ToolCall(
        tool=Tool(name="test", description=None, fn=_unused_tool),
        params=None,
        raw_args={"query": "weather"},
        context=ToolContext(),
    )

    async def terminal(tool_call: ToolCall) -> ActionResult:
        assert tool_call is call
        return ActionResult.success()

    with caplog.at_level(logging.INFO, logger="cara.tools.middleware.call_log"):
        result = asyncio.run(compose([CallLoggingMiddleware()], terminal)(call))

    assert result == ActionResult.success()
    assert any("[tool] test called with arguments: {'query': 'weather'}" in message for message in caplog.messages)
    assert any("[tool] test -> ok (" in message for message in caplog.messages)
