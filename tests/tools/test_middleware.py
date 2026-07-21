import asyncio
from pathlib import Path

from cara.file_system import Workspace
from cara.tools import (
    ActionResult,
    ErrorBoundaryMiddleware,
    ResultLimitMiddleware,
    Tool,
    ToolCall,
    ToolContext,
    ToolFeedbackError,
    ToolHandler,
    Tools,
    compose,
)


async def _unused_tool() -> ActionResult:
    return ActionResult.success()


def _call() -> ToolCall:
    return ToolCall(
        tool=Tool(name="test", description=None, fn=_unused_tool),
        params=None,
        raw_args={},
        context=ToolContext(),
    )


class RecordingMiddleware:
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
    assert events == [
        "outer:request",
        "inner:request",
        "tool",
        "inner:response",
        "outer:response",
    ]


def test_error_boundary_returns_expected_feedback() -> None:
    async def terminal(call: ToolCall) -> ActionResult:
        del call
        raise ToolFeedbackError("Try another value.")

    handler = compose([ErrorBoundaryMiddleware()], terminal)

    assert asyncio.run(handler(_call())) == ActionResult.fail("Try another value.")


def test_error_boundary_hides_unexpected_error() -> None:
    async def terminal(call: ToolCall) -> ActionResult:
        del call
        raise RuntimeError("host details")

    handler = compose([ErrorBoundaryMiddleware()], terminal)

    assert asyncio.run(handler(_call())) == ActionResult.fail("Internal tool error.")


def test_result_limit_changes_successful_response_on_the_way_out() -> None:
    async def terminal(call: ToolCall) -> ActionResult:
        del call
        return ActionResult.success("x" * 100)

    handler = compose([ResultLimitMiddleware(max_chars=30)], terminal)
    result = asyncio.run(handler(_call()))

    assert result.ok
    assert result.content is not None
    assert len(result.content) == 30
    assert result.content.endswith("[Output truncated.]")


def test_path_policy_blocks_escape_before_file_tool_runs(tmp_path: Path) -> None:
    tools = Tools(workspace=Workspace(tmp_path))
    outside_name = f"{tmp_path.name}-outside.txt"

    result = asyncio.run(
        tools.execute(
            "write_file",
            {"path": f"../{outside_name}", "content": "unsafe", "status": "Writing..."},
        )
    )

    assert not result.ok
    assert result.content is not None
    assert "outside the workspace" in result.content
    assert not (tmp_path.parent / outside_name).exists()


def test_path_policy_blocks_sensitive_file(tmp_path: Path) -> None:
    tools = Tools(workspace=Workspace(tmp_path))

    result = asyncio.run(
        tools.execute(
            "write_file",
            {"path": ".env", "content": "SECRET=value", "status": "Writing..."},
        )
    )

    assert not result.ok
    assert result.content is not None
    assert "blocked by the workspace path policy" in result.content
    assert not (tmp_path / ".env").exists()


def test_path_policy_matches_sensitive_paths_case_insensitively(tmp_path: Path) -> None:
    tools = Tools(workspace=Workspace(tmp_path))

    result = asyncio.run(
        tools.execute(
            "write_file",
            {"path": ".ENV", "content": "SECRET=value", "status": "Writing..."},
        )
    )

    assert not result.ok
    assert not (tmp_path / ".ENV").exists()


def test_content_size_middleware_blocks_large_write(tmp_path: Path) -> None:
    tools = Tools(workspace=Workspace(tmp_path))

    result = asyncio.run(
        tools.execute(
            "write_file",
            {"path": "large.txt", "content": "x" * 1_000_001, "status": "Writing..."},
        )
    )

    assert not result.ok
    assert result.content is not None
    assert "exceeds the 1000000-byte write limit" in result.content
    assert not (tmp_path / "large.txt").exists()


def test_custom_middleware_observes_policy_response(tmp_path: Path) -> None:
    events: list[str] = []
    tools = Tools(
        workspace=Workspace(tmp_path),
        middlewares=(RecordingMiddleware("custom", events),),
    )

    result = asyncio.run(
        tools.execute(
            "read_file",
            {"path": "../outside.txt", "status": "Reading..."},
        )
    )

    assert not result.ok
    assert events == ["custom:request", "custom:response"]
