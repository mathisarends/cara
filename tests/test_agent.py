import asyncio
from pathlib import Path

from agenttoolkit import Skills
from agenttoolkit.builtins import LocalWorkspace
from llmify import AssistantMessage, ChatInvokeCompletion, Function, ToolCall, ToolResultMessage, UserMessage

from cara.agent import Agent
from cara.tools import ActionResult, build_tools, create_tools
from cara.tools.params import WeatherParams

_ANSWER = "Hallo, wie kann ich helfen?"


def _skills(root: Path) -> Skills:
    directory = root / "weather"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: weather\ndescription: Wetter abrufen.\n---\nRufe weather_lookup auf.\n",
        encoding="utf-8",
    )
    return Skills.from_local_dir(root)


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


def test_agent_responds_to_normalized_text() -> None:
    llm = StaticChatModel()
    agent = Agent(llm=llm, tools=create_tools())

    answer = asyncio.run(agent.respond("  Hallo  "))

    assert answer == _ANSWER
    user_messages = [message for message in llm.messages[0] if isinstance(message, UserMessage)]
    assert [message.content for message in user_messages] == ["Hallo"]


def test_agent_continues_after_each_tool_round_until_final_answer(tmp_path: Path) -> None:
    async def run() -> tuple[str, MultiRoundToolChatModel]:
        llm = MultiRoundToolChatModel()
        tools = create_tools()

        @tools.action("Wetter abrufen.", name="weather_lookup", params=WeatherParams)
        async def weather_lookup(params: WeatherParams) -> ActionResult:
            return ActionResult.success("22 Grad und sonnig.")

        skills = _skills(tmp_path)
        agent = Agent(
            llm=llm,
            tools=build_tools(skills=skills, tools=tools),
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
        )

        await agent.respond("Schreibe außerhalb des Arbeitsbereichs.")
        return llm

    llm = asyncio.run(run())

    tool_results = [message for message in llm.messages[1] if isinstance(message, ToolResultMessage)]
    assert len(tool_results) == 1
    assert tool_results[0].tool_call_id == "write-outside-workspace"
    assert tool_results[0].content == "Internal tool error."
