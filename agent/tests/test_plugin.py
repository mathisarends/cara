import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from llmify import ChatModel, Function, Message, StreamEnd, StreamTextDelta, ToolCall
from pydantic import ValidationError

from agent.models import ModelSwitch
from agent.plugin import create_plugin
from agent.tools import AgentTools
from agent_plugin_api import (
    AgentAssistantMessage,
    AgentChannelRef,
    AgentContext,
    AgentPluginContext,
    AgentRunRequest,
    AgentSessionRef,
    AgentToolCall,
    AgentToolCallSequence,
    AgentToolCallState,
    AgentUserMessage,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnSteered,
)
from llm import CodexModel


class _SessionReader:
    def __init__(self, context: AgentContext) -> None:
        self._context = context
        self.requests: list[tuple[UUID, UUID]] = []

    async def context_for_turn(
        self,
        session_id: UUID,
        input_id: UUID,
    ) -> AgentContext:
        self.requests.append((session_id, input_id))
        return self._context


class _Model:
    def __init__(self) -> None:
        self.requests: list[list[Message]] = []
        self._turn = 0
        self.prewarm_calls = 0
        self.close_calls = 0

    async def prewarm(self) -> None:
        self.prewarm_calls += 1

    async def aclose(self) -> None:
        self.close_calls += 1

    async def stream(
        self,
        messages: list[Message],
        **options: Any,
    ) -> AsyncIterator[StreamTextDelta | StreamEnd]:
        del options
        self.requests.append(messages)
        if self._turn == 0:
            self._turn += 1
            yield StreamTextDelta(delta="Ich prüfe. ")
            yield StreamEnd(
                completion="Ich prüfe. ",
                stop_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        id="call-weather",
                        function=Function(
                            name="weather",
                            arguments='{"city":"Berlin"}',
                        ),
                    )
                ],
            )
            return
        yield StreamTextDelta(delta="Sonnig")
        yield StreamEnd(completion="Sonnig", stop_reason="stop")


class _Tools:
    def __init__(self, on_execute: Callable[[], Awaitable[None]] | None = None) -> None:
        self.closed = False
        self._on_execute = on_execute

    async def prepare(self) -> None:
        pass

    async def aclose(self) -> None:
        self.closed = True

    def get_schema(self, provider: str) -> list[object]:
        del provider
        return []

    async def execute(self, name: str, arguments: dict[str, Any]) -> object:
        assert name == "weather"
        assert arguments == {"city": "Berlin"}
        if self._on_execute is not None:
            await self._on_execute()
        return {"temperature": 22}


class _TurnDependency:
    pass


def test_cara_plugin_rebuilds_context_and_streams_complete_tool_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _Model()
    tools = _Tools()
    turn_dependency = _TurnDependency()
    resolved_turn_dependencies: list[_TurnDependency | None] = []
    model_switches: list[ModelSwitch] = []
    model_creations: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def create_test_model(*args: object, **kwargs: object) -> ChatModel:
        model_creations.append((args, kwargs))
        return cast(ChatModel, model)

    def build_test_tools(**kwargs: Any) -> AgentTools:
        tool_context = kwargs["context"]
        model_switches.append(cast(ModelSwitch, tool_context.resolve(ModelSwitch)))
        resolved_turn_dependencies.append(tool_context.resolve(_TurnDependency))
        return cast(AgentTools, tools)

    monkeypatch.setattr(
        "agent.factory.create_codex_model",
        create_test_model,
    )
    monkeypatch.setattr(
        "agent.factory.build_tools",
        build_test_tools,
    )
    monkeypatch.setattr(
        "agent.plugin.runner.turn_tool_dependencies",
        lambda request: (turn_dependency,),
    )
    context = AgentContext(
        (
            AgentUserMessage(uuid4(), "Vorherige Frage"),
            AgentToolCallSequence(
                uuid4(),
                (
                    AgentToolCall(
                        uuid4(),
                        "call-old-weather",
                        "weather",
                        {"city": "Hamburg"},
                        AgentToolCallState.COMPLETED,
                        result={"temperature": 18},
                    ),
                    AgentToolCall(
                        uuid4(),
                        "call-old-search",
                        "search",
                        {"query": "Cara"},
                        AgentToolCallState.FAILED,
                        error="timeout",
                    ),
                ),
            ),
            AgentAssistantMessage(uuid4(), "Vorherige Antwort"),
        )
    )
    sessions = _SessionReader(context)
    runner = create_plugin().create(
        {
            "models": ["gpt-5.3-codex-spark", "gpt-5.6-sol"],
            "workspace": {"root": str(tmp_path)},
        },
        AgentPluginContext(sessions),
    )
    session_id = uuid4()
    input_id = uuid4()
    request = AgentRunRequest(
        session=AgentSessionRef(session_id, AgentChannelRef("test")),
        turn_id=uuid4(),
        input_id=input_id,
        input="Wie ist das Wetter?",
    )

    async def run() -> list[object]:
        await runner.prepare(request.session)
        events = [event async for event in runner.run(request)]
        await runner.finish(request.session)
        await runner.close()
        return events

    events = asyncio.run(run())

    assert sessions.requests == [(session_id, input_id)]
    assert model_switches[0].names == (
        "gpt-5.3-codex-spark",
        "gpt-5.6-sol",
    )
    assert model_switches[0].current_name == "gpt-5.3-codex-spark"
    assert resolved_turn_dependencies == [turn_dependency]
    assert model_creations == [((CodexModel.SPARK,), {})]
    assert model.prewarm_calls == 1
    assert model.close_calls == 1
    assert [message.content for message in model.requests[0]] == [
        "",
        "Vorherige Frage",
        "",
        '{"temperature": 18}',
        "timeout",
        "Vorherige Antwort",
        "Wie ist das Wetter?",
    ]
    assert events == [
        ChatDelta("Ich prüfe. "),
        ToolCallStarted("call-weather", "weather", {"city": "Berlin"}),
        ToolCallCompleted(
            "call-weather",
            "weather",
            {"temperature": 22},
        ),
        ChatDelta("Sonnig"),
        ChatCompleted("Ich prüfe. Sonnig"),
    ]
    assert tools.closed


def test_cara_plugin_delivers_steering_at_the_next_tool_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _Model()
    request = AgentRunRequest(
        session=AgentSessionRef(uuid4(), AgentChannelRef("test")),
        turn_id=uuid4(),
        input_id=uuid4(),
        input="Wie ist das Wetter?",
    )
    runners: list[Any] = []

    async def steer_while_the_tool_runs() -> None:
        await runners[0].steer(request.session, "Und in Hamburg?")

    tools = _Tools(steer_while_the_tool_runs)
    monkeypatch.setattr(
        "agent.factory.create_codex_model",
        lambda *args, **kwargs: cast(ChatModel, model),
    )
    monkeypatch.setattr(
        "agent.factory.build_tools",
        lambda **kwargs: cast(AgentTools, tools),
    )
    runners.append(
        create_plugin().create(
            {"workspace": {"root": str(tmp_path)}},
            AgentPluginContext(_SessionReader(AgentContext(()))),
        )
    )

    async def run() -> list[object]:
        await runners[0].prepare(request.session)
        events = [event async for event in runners[0].run(request)]
        await runners[0].close()
        return events

    events = asyncio.run(run())

    assert TurnSteered("Und in Hamburg?") in events
    assert (
        events.index(TurnSteered("Und in Hamburg?"))
        == events.index(
            ToolCallCompleted("call-weather", "weather", {"temperature": 22})
        )
        + 1
    )
    # The steering reaches the model only in the request that follows the tool round.
    assert [message.content for message in model.requests[1]][-1] == "Und in Hamburg?"


def test_cara_plugin_rejects_unknown_configuration() -> None:
    sessions = _SessionReader(AgentContext(()))

    with pytest.raises(ValidationError, match="unknown"):
        create_plugin().create(
            {"unknown": True},
            AgentPluginContext(sessions),
        )


@pytest.mark.parametrize(
    "models",
    [[], ["gpt-5.6-sol", "gpt-5.6-sol"]],
)
def test_cara_plugin_rejects_invalid_model_lists(models: list[str]) -> None:
    sessions = _SessionReader(AgentContext(()))

    with pytest.raises(ValidationError, match="models"):
        create_plugin().create(
            {"models": models},
            AgentPluginContext(sessions),
        )


def test_cara_plugin_factory_returns_a_fresh_plugin() -> None:
    assert create_plugin() is not create_plugin()
