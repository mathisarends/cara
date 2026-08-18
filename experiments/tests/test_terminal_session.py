import asyncio
from pathlib import Path

from llmify import (
    Function,
    StreamEnd,
    StreamTextDelta,
    StreamToolCall,
    ToolCall,
    UserMessage,
)

from agent.agent import Agent
from agent.tools import create_tools
from experiments.agent_runner import AgentTurnRunner
from experiments.terminal import TerminalRenderer, TerminalSession


class EchoChatModel:
    def __init__(self) -> None:
        self.messages: list[list[object]] = []

    async def stream(self, messages, *, tools):
        self.messages.append(messages)
        user = next(
            message
            for message in reversed(messages)
            if isinstance(message, UserMessage)
        )
        completion = f"Antwort auf {user.content}"
        yield StreamTextDelta(delta="Antwort auf ")
        yield StreamTextDelta(delta=user.content)
        yield StreamEnd(completion=completion)


def test_terminal_session_sends_text_turns_to_agent(tmp_path: Path) -> None:
    inputs = iter((" Hallo ", "2", "/exit"))
    prompts: list[str] = []
    outputs: list[str] = []

    def read(prompt: str) -> str:
        prompts.append(prompt)
        return next(inputs)

    llm = EchoChatModel()
    session = TerminalSession(
        AgentTurnRunner(Agent(llm=llm, tools=create_tools(), prompt_root=tmp_path)),
        input_reader=read,
        renderer=TerminalRenderer(
            output_writer=outputs.append,
            stream_writer=outputs.append,
            color=False,
        ),
    )

    asyncio.run(session.run())

    assert prompts == ["you  ❯ ", "you  ❯ ", "you  ❯ "]
    assert outputs == [
        "cara ❯ ",
        "Antwort auf ",
        "Hallo",
        "\n",
        "cara ❯ ",
        "Antwort auf ",
        "2",
        "\n",
    ]
    assert len(llm.messages) == 2


def test_terminal_session_stops_at_end_of_input(tmp_path: Path) -> None:
    def end_of_input(prompt: str) -> str:
        raise EOFError

    session = TerminalSession(
        AgentTurnRunner(
            Agent(llm=EchoChatModel(), tools=create_tools(), prompt_root=tmp_path)
        ),
        input_reader=end_of_input,
    )

    asyncio.run(session.run())


def test_terminal_session_shows_tool_calls_and_results(tmp_path: Path) -> None:
    class ToolCallingChatModel:
        def __init__(self) -> None:
            self.calls = 0

        async def stream(self, messages, *, tools):
            self.calls += 1
            if self.calls == 1:
                tool_call = ToolCall(
                    id="weather-call",
                    function=Function(
                        name="weather_lookup",
                        arguments='{"location":"Aurich"}',
                    ),
                )
                yield StreamToolCall(tool_call=tool_call)
                yield StreamEnd(tool_calls=[tool_call], stop_reason="tool_calls")
                return
            completion = "15 Grad und teils bewölkt."
            yield StreamTextDelta(delta="15 Grad ")
            yield StreamTextDelta(delta="und teils bewölkt.")
            yield StreamEnd(completion=completion)

    inputs = iter(("Wie wird das Wetter?", "/exit"))
    outputs: list[str] = []
    tools = create_tools()

    @tools.action("Wetter abrufen.", name="weather_lookup")
    async def weather_lookup(location: str) -> str:
        return f"Wetter für {location}"

    session = TerminalSession(
        AgentTurnRunner(
            Agent(llm=ToolCallingChatModel(), tools=tools, prompt_root=tmp_path)
        ),
        input_reader=lambda prompt: next(inputs),
        renderer=TerminalRenderer(
            output_writer=outputs.append,
            stream_writer=outputs.append,
            color=False,
        ),
    )

    asyncio.run(session.run())

    assert outputs == [
        '╭─ tool  weather_lookup\n│  {\n│    "location": "Aurich"\n│  }',
        "╰─ done  weather_lookup\n   Wetter für Aurich",
        "cara ❯ ",
        "15 Grad ",
        "und teils bewölkt.",
        "\n",
    ]
