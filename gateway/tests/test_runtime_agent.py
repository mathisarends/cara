import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from agenttoolkit import Skills
from llmify import AssistantMessage as LLMifyAssistantMessage
from llmify import (
    Function,
    StreamEnd,
    StreamTextDelta,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
)

from agent import AgentContext, StoredToolCall, SystemPromptComposer
from gateway.features.conversation.application import AgentEventBus
from gateway.features.conversation.domain import (
    ChatCompleted,
    ChatDelta,
    Session,
    SessionRepository,
    ToolCallCompleted,
    ToolCallStarted,
)
from gateway.features.conversation.infrastructure import RuntimeAgentRunner


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
            yield StreamTextDelta(delta="Ich schaue nach.")
            yield StreamEnd(
                completion="Ich schaue nach.",
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


def test_agent_context_recombines_progress_text_with_following_tool_calls(
    tmp_path: Path,
) -> None:
    context = AgentContext(SystemPromptComposer(root=tmp_path))
    context.add_assistant_message("Ich schaue nach.")
    context.add_tool_calls(
        [
            StoredToolCall(
                call_id="call-1",
                name="lookup",
                arguments={"query": "Cara"},
                result={"answer": "Cara"},
            )
        ]
    )

    assistant_message = context.to_llm_messages()[1]

    assert isinstance(assistant_message, LLMifyAssistantMessage)
    assert assistant_message.content == "Ich schaue nach."
    assert assistant_message.tool_calls[0].id == "call-1"


def test_runtime_agent_executes_catalog_tools_and_emits_lifecycle_events(
    tmp_path: Path,
) -> None:
    async def run():
        (tmp_path / "AGENTS.md").write_text(
            "Runtime system context.",
            encoding="utf-8",
        )
        skill_root = tmp_path / "skills" / "spogo-cli"
        skill_root.mkdir(parents=True)
        skill_file = skill_root / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "name: spogo-cli\n"
            "description: Initial description.\n"
            "---\n"
            "Use the spogo CLI.\n",
            encoding="utf-8",
        )
        skills = Skills.from_dir(tmp_path / "skills")
        skill_file.write_text(
            "---\n"
            "name: spogo-cli\n"
            "description: Control Spotify with Spogo.\n"
            "---\n"
            "Use the spogo CLI.\n",
            encoding="utf-8",
        )
        session = Session.create()
        session.add_user_message("Suche Cara")
        model = _ToolCallingModel()
        tools = _Tools()

        @asynccontextmanager
        async def tool_factory():
            yield tools

        runner = RuntimeAgentRunner(
            sessions=_SessionRepository(session),
            llm=model,
            tool_factory=tool_factory,
            prompt_root=tmp_path,
            skills=skills,
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
        ChatDelta,
        ChatCompleted,
        ToolCallStarted,
        ToolCallCompleted,
        ChatDelta,
        ChatCompleted,
    ]
    assert events[0].text == "Ich schaue nach."
    assert events[1].text == "Ich schaue nach."
    assert events[1].finish_reason == "tool_calls"
    assert events[2].call_id == "call-1"
    assert events[2].arguments == {"query": "Cara"}
    assert events[3].result == {"answer": "Cara"}
    assert events[4].text == "Gefunden"
    assert events[5].text == "Gefunden"
    assert events[5].finish_reason == "stop"
    second_round_messages = model.calls[1][0]
    system_message = model.calls[0][0][0]
    assert isinstance(system_message, SystemMessage)
    assert "Runtime system context." in system_message.content
    assert "<name>spogo-cli</name>" in system_message.content
    assert "<description>Control Spotify with Spogo.</description>" in (
        system_message.content
    )
    tool_result = next(
        message
        for message in second_round_messages
        if isinstance(message, ToolResultMessage)
    )
    assert tool_result.tool_call_id == "call-1"
    assert tool_result.content == '{"answer": "Cara"}'
    assistant_tool_call = next(
        message
        for message in second_round_messages
        if isinstance(message, LLMifyAssistantMessage) and message.tool_calls
    )
    assert assistant_tool_call.content == "Ich schaue nach."
