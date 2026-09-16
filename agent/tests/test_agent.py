from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest

from agent.agent import Agent
from agent.events import ToolCompleted, ToolStarted, TurnCompleted
from agent.tools import AgentTools, FatalToolError
from llm import ChatModel, Message, ModelResponse, ToolCall


class _Model:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = iter(responses)
        self.requests: list[list[Message]] = []

    async def stream(
        self,
        messages: list[Message],
        **options: Any,
    ) -> AsyncIterator[ModelResponse]:
        del options
        self.requests.append(messages)
        yield next(self._responses)

    async def aclose(self) -> None:
        pass


class _Tools:
    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self._failures = failures or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.schema_formats: list[str] = []

    def get_schema(self, schema_format: str = "native") -> list[object]:
        self.schema_formats.append(schema_format)
        return []

    async def execute(self, name: str, arguments: dict[str, Any]) -> object:
        self.calls.append((name, arguments))
        if error := self._failures.get(name):
            raise error
        return f"result:{name}"


def _tool_call(call_id: str, name: str, arguments: str) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


def _agent(model: _Model, tools: _Tools) -> Agent:
    return Agent(
        model=cast(ChatModel, model),
        tools=cast(AgentTools, tools),
        workspace_root=Path("missing-test-workspace"),
    )


async def _run_turn(agent: Agent, text: str) -> list[object]:
    events = await agent.start_turn(text)
    return [event async for event in events]


async def test_tool_errors_become_results_and_the_turn_continues() -> None:
    calls = [
        _tool_call("bad-json", "broken", "{"),
        _tool_call("bad-shape", "wrong_shape", "[]"),
        _tool_call("crash", "crash", "{}"),
        _tool_call("ok", "working", '{"value": 1}'),
    ]
    model = _Model(
        [
            ModelResponse(finish_reason="tool_calls", tool_calls=tuple(calls)),
            ModelResponse(completion="recovered", finish_reason="stop"),
        ]
    )
    tools = _Tools({"crash": RuntimeError("boom")})
    agent = _agent(model, tools)

    try:
        events = await _run_turn(agent, "go")
    finally:
        await agent.aclose()

    assert [event.call_id for event in events if isinstance(event, ToolStarted)] == [
        "bad-json",
        "bad-shape",
        "crash",
        "ok",
    ]
    completed = [event for event in events if isinstance(event, ToolCompleted)]
    assert [event.is_error for event in completed] == [True, True, True, False]
    assert completed[0].result.startswith("JSONDecodeError:")
    assert completed[1].result == (
        "ValueError: Tool arguments for 'wrong_shape' must be an object"
    )
    assert completed[2].result == "RuntimeError: boom"
    assert tools.calls == [("crash", {}), ("working", {"value": 1})]
    assert [message.content for message in model.requests[1]][-4:] == [
        completed[0].result,
        completed[1].result,
        completed[2].result,
        "result:working",
    ]
    assert events[-1] == TurnCompleted("recovered")


async def test_repeated_tool_failure_nudges_the_model_to_update_the_user() -> None:
    model = _Model(
        [
            ModelResponse(
                finish_reason="tool_calls",
                tool_calls=(_tool_call("one", "crash", "{}"),),
            ),
            ModelResponse(
                finish_reason="tool_calls",
                tool_calls=(_tool_call("two", "crash", "{}"),),
            ),
            ModelResponse(completion="it keeps failing", finish_reason="stop"),
        ]
    )
    agent = _agent(model, _Tools({"crash": RuntimeError("boom")}))

    try:
        await _run_turn(agent, "go")
    finally:
        await agent.aclose()

    assert model.requests[1][-1].content == "RuntimeError: boom"
    assert model.requests[2][-1].content.startswith(
        "RuntimeError: boom\n\n[Runtime note] `crash` has failed 2 times"
    )


async def test_fatal_tool_error_aborts_the_turn() -> None:
    model = _Model(
        [
            ModelResponse(
                finish_reason="tool_calls",
                tool_calls=(
                    _tool_call("fatal", "fatal", "{}"),
                    _tool_call("later", "later", "{}"),
                ),
            ),
            ModelResponse(completion="recovered", finish_reason="stop"),
        ]
    )
    tools = _Tools({"fatal": FatalToolError("sandbox unavailable")})
    agent = _agent(model, tools)

    try:
        with pytest.raises(FatalToolError, match="sandbox unavailable"):
            await _run_turn(agent, "go")
        await _run_turn(agent, "retry")
    finally:
        await agent.aclose()

    assert tools.calls == [("fatal", {})]
    assert [message.content for message in model.requests[1]][-2:] == ["go", "retry"]


async def test_start_turn_rejects_a_parallel_turn() -> None:
    model = _Model([ModelResponse(completion="done")])
    tools = _Tools()
    agent = _agent(model, tools)

    first = await agent.start_turn("first")
    try:
        with pytest.raises(RuntimeError, match="A turn is already running"):
            await agent.start_turn("second")
        assert [event async for event in first][-1] == TurnCompleted("done")
    finally:
        await agent.aclose()


async def test_stale_steering_is_discarded_before_the_next_turn() -> None:
    model = _Model(
        [
            ModelResponse(completion="first"),
            ModelResponse(completion="second"),
        ]
    )
    agent = _agent(model, _Tools())

    try:
        await _run_turn(agent, "one")
        await agent.steer("too late")
        await _run_turn(agent, "two")
    finally:
        await agent.aclose()

    assert [message.content for message in model.requests[1]][-1] == "two"
    assert "too late" not in [
        message.content for request in model.requests for message in request
    ]


async def test_tools_are_reused_across_turns() -> None:
    model = _Model([ModelResponse(completion="one"), ModelResponse(completion="two")])
    tools = _Tools()
    agent = _agent(model, tools)

    await _run_turn(agent, "one")
    await _run_turn(agent, "two")
    assert tools.schema_formats == ["native", "native"]

    await agent.aclose()
    await agent.aclose()
