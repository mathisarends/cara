import asyncio
from pathlib import Path
from typing import cast

import pytest
from llmify import AssistantMessage, ChatInvokeCompletion, ChatModel, Function, ToolCall, ToolResultMessage

from cara.file_system import Workspace
from cara.subagent import Subagent
from cara.tools import Tools
from cara.tools.sandbox import BashSandboxRequest, BashSandboxResult


class _BashSandbox:
    def __init__(self) -> None:
        self.commands: list[str] = []

    async def run(self, request: BashSandboxRequest) -> BashSandboxResult:
        self.commands.append(request.command)
        return BashSandboxResult(return_code=0, output="hello from sandbox")


class _ToolCallingModel:
    def __init__(self) -> None:
        self.messages: list[list[object]] = []
        self.schemas: list[list[dict]] = []

    async def invoke(self, messages, *, tools):
        self.messages.append(messages)
        self.schemas.append(tools)
        if len(self.messages) == 1:
            tool_call = ToolCall(
                id="bash-1",
                function=Function(name="bash", arguments='{"command":"printf hello"}'),
            )
            return ChatInvokeCompletion(completion="", tool_calls=[tool_call])
        return ChatInvokeCompletion(completion="The sandbox printed hello.")


def test_subagent_calls_tools_until_it_has_a_text_response(tmp_path: Path) -> None:
    model = _ToolCallingModel()
    sandbox = _BashSandbox()
    tools = Tools(workspace=Workspace(tmp_path), bash_sandbox=sandbox)
    agent = Subagent(llm=cast(ChatModel, model), tools=tools, system_prompt="Test prompt")

    answer = asyncio.run(agent.run("Run printf"))

    assert answer == "The sandbox printed hello."
    assert sandbox.commands == ["printf hello"]
    assert any(schema["function"]["name"] == "bash" for schema in model.schemas[0])

    assistant_calls = [message for message in model.messages[1] if isinstance(message, AssistantMessage)]
    tool_results = [message for message in model.messages[1] if isinstance(message, ToolResultMessage)]
    assert assistant_calls[-1].tool_calls[0].id == "bash-1"
    assert [(result.tool_call_id, result.content) for result in tool_results] == [("bash-1", "hello from sandbox")]


def test_subagent_keeps_conversation_history() -> None:
    class Model:
        def __init__(self) -> None:
            self.messages = []

        async def invoke(self, messages, *, tools):
            self.messages.append(messages)
            return ChatInvokeCompletion(completion=f"answer {len(self.messages)}")

    model = Model()
    agent = Subagent(llm=cast(ChatModel, model), system_prompt="System")

    assert asyncio.run(agent.run("first")) == "answer 1"
    assert asyncio.run(agent.run("second")) == "answer 2"
    assert [message.content for message in model.messages[1]] == [
        "System",
        "first",
        "answer 1",
        "second",
    ]


def test_subagent_stops_after_configured_tool_round_limit(tmp_path: Path) -> None:
    class Model:
        async def invoke(self, messages, *, tools):
            return ChatInvokeCompletion(
                completion="",
                tool_calls=[
                    ToolCall(
                        id="bash-loop",
                        function=Function(name="bash", arguments='{"command":"true"}'),
                    )
                ],
            )

    agent = Subagent(
        llm=cast(ChatModel, Model()),
        tools=Tools(workspace=Workspace(tmp_path), bash_sandbox=_BashSandbox()),
        max_tool_rounds=2,
    )

    with pytest.raises(RuntimeError, match="exceeded 2 consecutive tool rounds"):
        asyncio.run(agent.run("loop"))
