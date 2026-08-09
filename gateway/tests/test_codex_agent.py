import asyncio
from contextlib import asynccontextmanager

from llmify import Function, StreamEnd, StreamTextDelta, ToolCall, ToolResultMessage

from gateway.features.conversation.application import AgentEventBus
from gateway.features.conversation.domain import (
    ChatCompleted,
    ChatDelta,
    Session,
    SessionRepository,
    ToolCallCompleted,
    ToolCallStarted,
)
from gateway.features.conversation.infrastructure import CodexAgentRunner


class _SessionRepository(SessionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    async def find_by_id(self, id):
        return self._session if self._session.id == id else None

    async def save(self, domain):
        self._session = domain
        return domain

    async def claim_turn(self, id):
        return True

    async def release_turn(self, id):
        pass


class _Tools:
    def get_schema(self, schema_format):
        assert schema_format == "openai"
        return [{"type": "function", "function": {"name": "lookup"}}]

    async def execute(self, name, arguments):
        assert name == "lookup"
        return {"answer": arguments["query"]}


class _ToolCallingModel:
    def __init__(self) -> None:
        self.calls = []

    async def stream(self, messages, *, tools):
        self.calls.append((messages, tools))
        if len(self.calls) == 1:
            yield StreamEnd(
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        function=Function(
                            name="lookup",
                            arguments='{"query":"Cara"}',
                        ),
                    )
                ],
                stop_reason="tool_calls",
            )
            return

        yield StreamTextDelta(delta="Gefunden")
        yield StreamEnd(completion="Gefunden", stop_reason="stop")


def test_codex_agent_executes_catalog_tools_and_emits_lifecycle_events() -> None:
    async def run():
        session = Session.create()
        session.add_user_message("Suche Cara")
        model = _ToolCallingModel()
        tools = _Tools()

        @asynccontextmanager
        async def tool_factory():
            yield tools

        runner = CodexAgentRunner(
            sessions=_SessionRepository(session),
            llm=model,
            tool_factory=tool_factory,
        )
        event_bus = AgentEventBus()
        events = []

        async def capture(event):
            events.append(event)

        event_bus.on(ToolCallStarted, capture)
        event_bus.on(ToolCallCompleted, capture)
        event_bus.on(ChatDelta, capture)
        event_bus.on(ChatCompleted, capture)

        await runner.run(session.id, {}, event_bus)
        return model, events

    model, events = asyncio.run(run())

    assert [type(event) for event in events] == [
        ToolCallStarted,
        ToolCallCompleted,
        ChatDelta,
        ChatCompleted,
    ]
    assert events[0].call_id == "call-1"
    assert events[0].arguments == {"query": "Cara"}
    assert events[1].result == {"answer": "Cara"}
    assert events[2].text == "Gefunden"
    assert events[3].text == "Gefunden"
    second_round_messages = model.calls[1][0]
    tool_result = next(
        message
        for message in second_round_messages
        if isinstance(message, ToolResultMessage)
    )
    assert tool_result.tool_call_id == "call-1"
    assert tool_result.content == '{"answer": "Cara"}'
