from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from llmify import ChatModel, Function, Message, StreamEnd, ToolCall

from agent.agent import Agent
from agent.events import ToolCompleted, ToolStarted, TurnCompleted
from agent.models import ModelSwitch
from agent.tools import AgentTools, FatalToolError


class _Model:
    def __init__(self, responses: list[StreamEnd]) -> None:
        self._responses = iter(responses)
        self.requests: list[list[Message]] = []

    async def stream(
        self,
        messages: list[Message],
        **options: Any,
    ) -> AsyncIterator[StreamEnd]:
        del options
        self.requests.append(messages)
        yield next(self._responses)


class _Tools:
    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self._failures = failures or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.prepare_calls = 0
        self.close_calls = 0
        self.schema_formats: list[str] = []

    async def prepare(self) -> None:
        self.prepare_calls += 1

    async def aclose(self) -> None:
        self.close_calls += 1

    def get_schema(self, schema_format: str = "native") -> list[object]:
        self.schema_formats.append(schema_format)
        return []

    async def execute(self, name: str, arguments: dict[str, Any]) -> object:
        self.calls.append((name, arguments))
        if error := self._failures.get(name):
            raise error
        return f"result:{name}"


def _tool_call(call_id: str, name: str, arguments: str) -> ToolCall:
    return ToolCall(
        id=call_id,
        function=Function(name=name, arguments=arguments),
    )


def _agent(model: _Model, tools: _Tools) -> Agent:
    return Agent(
        models=ModelSwitch.single(cast(ChatModel, model)),
        tools=cast(AgentTools, tools),
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
            StreamEnd(stop_reason="tool_calls", tool_calls=calls),
            StreamEnd(completion="recovered", stop_reason="stop"),
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


async def test_fatal_tool_error_aborts_the_turn() -> None:
    model = _Model(
        [
            StreamEnd(
                stop_reason="tool_calls",
                tool_calls=[
                    _tool_call("fatal", "fatal", "{}"),
                    _tool_call("later", "later", "{}"),
                ],
            ),
            StreamEnd(completion="recovered", stop_reason="stop"),
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
    model = _Model([StreamEnd(completion="done")])
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
            StreamEnd(completion="first"),
            StreamEnd(completion="second"),
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


async def test_tools_live_for_the_agent_lifetime() -> None:
    model = _Model([StreamEnd(completion="one"), StreamEnd(completion="two")])
    tools = _Tools()
    agent = _agent(model, tools)

    await _run_turn(agent, "one")
    await _run_turn(agent, "two")
    assert tools.prepare_calls == 1
    assert tools.close_calls == 0
    assert tools.schema_formats == ["native", "native"]

    await agent.aclose()
    await agent.aclose()
    assert tools.close_calls == 1
