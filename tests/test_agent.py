import asyncio
from pathlib import Path

from agenttoolkit import Skills
from agenttoolkit.builtins import LocalWorkspace
from llmify import (
    AssistantMessage,
    ChatInvokeCompletion,
    ChatOpenAIResponses,
    ContinuationMode,
    Function,
    OpenAIResponsesCompletion,
    OpenAIResponsesState,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

from cara.agent import Agent
from cara.tools import build_tools, create_tools
from cara.tools.params import WeatherParams

_ANSWER = "Hallo, wie kann ich helfen?"


def _skills(root: Path) -> Skills:
    directory = root / "weather"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: weather\ndescription: Wetter abrufen.\n---\nRufe weather_lookup auf.\n",
        encoding="utf-8",
    )
    return Skills.from_dir(root)


class StaticChatModel:
    def __init__(self) -> None:
        self.messages: list[list[object]] = []

    async def invoke(self, messages, *, tools):
        self.messages.append(messages)
        return ChatInvokeCompletion(completion=_ANSWER)


class MultiRoundToolChatModel:
    def __init__(self) -> None:
        self.messages: list[list[object]] = []

    async def invoke(self, messages, *, tools):
        self.messages.append(messages)
        if len(self.messages) == 1:
            tool_call = ToolCall(
                id="load-weather-skill",
                function=Function(
                    name="load_skill",
                    arguments='{"name":"weather"}',
                ),
            )
            return ChatInvokeCompletion(completion="", tool_calls=[tool_call], stop_reason="tool_calls")
        if len(self.messages) == 2:
            tool_call = ToolCall(
                id="fetch-weather",
                function=Function(
                    name="weather_lookup",
                    arguments="{}",
                ),
            )
            return ChatInvokeCompletion(completion="", tool_calls=[tool_call], stop_reason="tool_calls")

        return ChatInvokeCompletion(completion="Heute sind es 22 Grad und es ist sonnig.")


class DeniedPathChatModel:
    def __init__(self) -> None:
        self.messages: list[list[object]] = []

    async def invoke(self, messages, *, tools):
        self.messages.append(messages)
        if len(self.messages) == 1:
            tool_call = ToolCall(
                id="write-outside-workspace",
                function=Function(
                    name="write_file",
                    arguments='{"path":"../outside.txt","content":"unsafe"}',
                ),
            )
            return ChatInvokeCompletion(completion="", tool_calls=[tool_call], stop_reason="tool_calls")

        return ChatInvokeCompletion(completion="Ich kann nur innerhalb des Arbeitsbereichs schreiben.")


class StatefulResponsesChatModel(ChatOpenAIResponses):
    def __init__(self) -> None:
        self.calls: list[tuple[list[object], OpenAIResponsesState | None]] = []

    async def invoke_with_tools(self, messages, *, provider_state, **kwargs):
        self.calls.append((messages, provider_state))
        state = OpenAIResponsesState(
            continuation_mode=ContinuationMode.PREVIOUS_RESPONSE_ID,
            response_id=f"response-{len(self.calls)}",
        )
        return OpenAIResponsesCompletion(completion=f"answer-{len(self.calls)}", provider_state=state)


def test_agent_responds_to_normalized_text(tmp_path: Path) -> None:
    llm = StaticChatModel()
    agent = Agent(llm=llm, tools=create_tools(), prompt_root=tmp_path)

    answer = asyncio.run(agent.respond("  Hallo  "))

    assert answer == _ANSWER
    user_messages = [message for message in llm.messages[0] if isinstance(message, UserMessage)]
    assert [message.content for message in user_messages] == ["Hallo"]


def test_agent_reuses_native_responses_state_without_replaying_chat_history(tmp_path: Path) -> None:
    async def run() -> StatefulResponsesChatModel:
        llm = StatefulResponsesChatModel()
        agent = Agent(llm=llm, tools=create_tools(), prompt_root=tmp_path)

        await agent.respond("Erste Frage")
        await agent.respond("Zweite Frage")
        return llm

    llm = asyncio.run(run())

    first_messages, first_state = llm.calls[0]
    second_messages, second_state = llm.calls[1]
    assert first_state is None
    assert [type(message) for message in first_messages] == [SystemMessage, UserMessage]
    assert [type(message) for message in second_messages] == [SystemMessage, UserMessage]
    assert second_messages[-1].content == "Zweite Frage"
    assert second_state is not None
    assert second_state.response_id == "response-1"


def test_agent_sends_workspace_memory(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("Remember this.", encoding="utf-8")
    llm = StaticChatModel()
    agent = Agent(llm=llm, tools=create_tools(), prompt_root=tmp_path)

    asyncio.run(agent.respond("Hallo"))

    system_message = llm.messages[0][0]
    assert "<memory>" in system_message.content
    assert "Remember this." in system_message.content


def test_agent_continues_after_each_tool_round_until_final_answer(tmp_path: Path) -> None:
    async def run() -> tuple[str, MultiRoundToolChatModel]:
        llm = MultiRoundToolChatModel()
        tools = create_tools()

        @tools.action("Wetter abrufen.", name="weather_lookup", params=WeatherParams)
        async def weather_lookup(params: WeatherParams) -> str:
            return "22 Grad und sonnig."

        skills = _skills(tmp_path)
        agent = Agent(
            llm=llm,
            tools=build_tools(skills=skills, tools=tools),
            prompt_root=tmp_path,
            skills=skills,
        )
        answer = await agent.respond("Wie wird das Wetter?")
        return answer, llm

    answer, llm = asyncio.run(run())

    assert answer == "Heute sind es 22 Grad und es ist sonnig."
    assert len(llm.messages) == 3

    second_round_results = [message for message in llm.messages[1] if isinstance(message, ToolResultMessage)]
    assert [(result.tool_call_id, result.content) for result in second_round_results] == [
        ("load-weather-skill", "Rufe weather_lookup auf.")
    ]
    third_round_calls = [message for message in llm.messages[2] if isinstance(message, AssistantMessage)]
    third_round_results = [message for message in llm.messages[2] if isinstance(message, ToolResultMessage)]
    assert [call.tool_calls[0].id for call in third_round_calls if call.tool_calls] == [
        "load-weather-skill",
        "fetch-weather",
    ]
    assert [(result.tool_call_id, result.content) for result in third_round_results] == [
        ("load-weather-skill", "Rufe weather_lookup auf."),
        ("fetch-weather", "22 Grad und sonnig."),
    ]


def test_tool_error_is_sent_to_the_model_as_a_tool_result(tmp_path: Path) -> None:
    async def run() -> DeniedPathChatModel:
        llm = DeniedPathChatModel()
        agent = Agent(
            llm=llm,
            tools=build_tools(tools=create_tools(), workspace=LocalWorkspace(tmp_path)),
            prompt_root=tmp_path,
        )

        await agent.respond("Schreibe außerhalb des Arbeitsbereichs.")
        return llm

    llm = asyncio.run(run())

    tool_results = [message for message in llm.messages[1] if isinstance(message, ToolResultMessage)]
    assert len(tool_results) == 1
    assert tool_results[0].tool_call_id == "write-outside-workspace"
    assert tool_results[0].content.startswith("Tool failed:")
