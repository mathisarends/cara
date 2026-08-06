import asyncio
from pathlib import Path

from llmify import Function, StreamEnd, StreamTextDelta, StreamToolCall, ToolCall, UserMessage
from transitbus import EventBus

from cara.agent import Agent
from cara.events import (
    AssistantTurnStarted,
    SessionEnded,
    SessionStarted,
    ToolCallFinished,
    ToolCallStarted,
    UserTurnStarted,
)
from cara.sessions import TerminalSession
from cara.tools import create_tools


class EchoChatModel:
    def __init__(self) -> None:
        self.messages: list[list[object]] = []

    async def stream(self, messages, *, tools):
        self.messages.append(messages)
        user = next(message for message in reversed(messages) if isinstance(message, UserMessage))
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
        Agent(llm=llm, tools=create_tools(), prompt_root=tmp_path),
        input_reader=read,
        output_writer=outputs.append,
        stream_writer=outputs.append,
        color=False,
    )

    asyncio.run(session.run())

    assert prompts == ["you  \u276f ", "you  \u276f ", "you  \u276f "]
    assert outputs == [
        "cara \u276f ",
        "Antwort auf ",
        "Hallo",
        "\n",
        "cara \u276f ",
        "Antwort auf ",
        "2",
        "\n",
    ]
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
            completion = "15 Grad und teils bew\u00f6lkt."
            yield StreamTextDelta(delta="15 Grad ")
            yield StreamTextDelta(delta="und teils bew\u00f6lkt.")
            yield StreamEnd(completion=completion)

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
        stream_writer=outputs.append,
        color=False,
    )

    asyncio.run(session.run())

    assert outputs == [
        '\u256d\u2500 tool  weather_lookup\n\u2502  {\n\u2502    "location": "Aurich"\n\u2502  }',
        "\u2570\u2500 done  weather_lookup\n   Wetter f\u00fcr Aurich",
        "cara \u276f ",
        "15 Grad ",
        "und teils bew\u00f6lkt.",
        "\n",
    ]


def test_terminal_session_emits_turn_and_tool_lifecycle(tmp_path: Path) -> None:
    class ToolCallingChatModel:
        def __init__(self) -> None:
            self._calls = 0

        async def stream(self, messages, *, tools):
            self._calls += 1
            if self._calls == 1:
                tool_call = ToolCall(id="call", function=Function(name="lookup", arguments="{}"))
                yield StreamEnd(tool_calls=[tool_call], stop_reason="tool_calls")
                return
            yield StreamEnd(completion="done")

    async def run() -> list[str]:
        events: list[str] = []
        event_bus = EventBus()

        async def capture_session_started(event: SessionStarted) -> None:
            events.append("session")

        async def capture_user(event: UserTurnStarted) -> None:
            events.append("user")

        async def capture_assistant(event: AssistantTurnStarted) -> None:
            events.append("assistant")

        async def capture_tool_started(event: ToolCallStarted) -> None:
            events.append(f"tool:{event.tool_name}")

        async def capture_tool_finished(event: ToolCallFinished) -> None:
            events.append(f"model:{event.tool_name}")

        async def capture_session_ended(event: SessionEnded) -> None:
            events.append("ended")

        for handler in (
            capture_session_started,
            capture_user,
            capture_assistant,
            capture_tool_started,
            capture_tool_finished,
            capture_session_ended,
        ):
            event_bus.subscribe(handler)

        tools = create_tools()

        @tools.action("Look up.", name="lookup")
        async def lookup() -> str:
            return "result"

        inputs = iter(("hello", "/exit"))
        agent = Agent(llm=ToolCallingChatModel(), tools=tools, prompt_root=tmp_path, event_bus=event_bus)
        session = TerminalSession(
            agent,
            input_reader=lambda prompt: next(inputs),
            stream_writer=lambda text: None,
            event_bus=event_bus,
        )
        await session.run()
        return events

    assert asyncio.run(run()) == [
        "session",
        "user",
        "assistant",
        "tool:lookup",
        "model:lookup",
        "user",
        "ended",
    ]
