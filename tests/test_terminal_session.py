import asyncio
from pathlib import Path

from llmify import ChatInvokeCompletion, Function, ToolCall, UserMessage

from cara.agent import Agent
from cara.sessions import TerminalSession
from cara.tools import create_tools


class EchoChatModel:
    def __init__(self) -> None:
        self.messages: list[list[object]] = []

    async def invoke(self, messages, *, tools):
        self.messages.append(messages)
        user = next(message for message in reversed(messages) if isinstance(message, UserMessage))
        return ChatInvokeCompletion(completion=f"Antwort auf {user.content}")


def test_terminal_session_sends_text_turns_to_agent(tmp_path: Path) -> None:
    inputs = iter((" Hallo ", "2", "/exit"))
    prompts: list[str] = []
    outputs: list[str] = []

    def read(prompt: str) -> str:
        prompts.append(prompt)
        return next(inputs)

    llm = EchoChatModel()
    session = TerminalSession(
        Agent(llm=llm, tools=create_tools(), prompt_root=tmp_path),
        input_reader=read,
        output_writer=outputs.append,
    )

    asyncio.run(session.run())

    assert prompts == ["> ", "> ", "> "]
    assert outputs == ["Antwort auf Hallo", "Antwort auf 2"]
    assert len(llm.messages) == 2


def test_terminal_session_stops_at_end_of_input(tmp_path: Path) -> None:
    def end_of_input(prompt: str) -> str:
        raise EOFError

    session = TerminalSession(
        Agent(llm=EchoChatModel(), tools=create_tools(), prompt_root=tmp_path),
        input_reader=end_of_input,
    )

    asyncio.run(session.run())


def test_terminal_session_shows_tool_calls_and_results(tmp_path: Path) -> None:
    class ToolCallingChatModel:
        def __init__(self) -> None:
            self.calls = 0

        async def invoke(self, messages, *, tools):
            self.calls += 1
            if self.calls == 1:
                return ChatInvokeCompletion(
                    completion="",
                    tool_calls=[
                        ToolCall(
                            id="weather-call",
                            function=Function(
                                name="weather_lookup",
                                arguments='{"location":"Aurich"}',
                            ),
                        )
                    ],
                    stop_reason="tool_calls",
                )
            return ChatInvokeCompletion(completion="15 Grad und teils bewölkt.")

    inputs = iter(("Wie wird das Wetter?", "/exit"))
    outputs: list[str] = []
    tools = create_tools()

    @tools.action("Wetter abrufen.", name="weather_lookup")
    async def weather_lookup(location: str) -> str:
        return f"Wetter für {location}"

    session = TerminalSession(
        Agent(llm=ToolCallingChatModel(), tools=tools, prompt_root=tmp_path),
        input_reader=lambda prompt: next(inputs),
        output_writer=outputs.append,
    )

    asyncio.run(session.run())

    assert outputs == [
        '[tool] weather_lookup {"location": "Aurich"}',
        "[tool result] weather_lookup: Wetter für Aurich",
        "15 Grad und teils bewölkt.",
    ]
