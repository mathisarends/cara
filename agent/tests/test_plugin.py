import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from llmify import ChatModel, Function, Message, StreamEnd, StreamTextDelta, ToolCall
from pydantic import ValidationError

from agent.plugin import plugin
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
)


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
    def __init__(self) -> None:
        self.closed = False

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
        return {"temperature": 22}


def test_cara_plugin_rebuilds_context_and_streams_complete_tool_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _Model()
    tools = _Tools()
    monkeypatch.setattr(
        "agent.plugin.create_codex_model",
        lambda *args, **kwargs: cast(ChatModel, model),
    )
    monkeypatch.setattr(
        "agent.plugin.build_tools",
        lambda **kwargs: cast(AgentTools, tools),
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
    runner = plugin.create(
        {"workspace_root": str(tmp_path)},
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
        events = [event async for event in runner.run(request)]
        await runner.close()
        return events

    events = asyncio.run(run())

    assert sessions.requests == [(session_id, input_id)]
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


def test_cara_plugin_rejects_unknown_configuration() -> None:
    sessions = _SessionReader(AgentContext(()))

    with pytest.raises(ValidationError, match="unknown"):
        plugin.create(
            {"unknown": True},
            AgentPluginContext(sessions),
        )
