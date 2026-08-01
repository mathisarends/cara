import asyncio

from llmify import ChatInvokeCompletion, UserMessage

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


def test_terminal_session_sends_text_turns_to_agent() -> None:
    inputs = iter((" Hallo ", "2", "/exit"))
    prompts: list[str] = []
    outputs: list[str] = []

    def read(prompt: str) -> str:
        prompts.append(prompt)
        return next(inputs)

    llm = EchoChatModel()
    session = TerminalSession(
        Agent(llm=llm, tools=create_tools()),
        input_reader=read,
        output_writer=outputs.append,
    )

    asyncio.run(session.run())

    assert prompts == ["> ", "> ", "> "]
    assert outputs == ["Antwort auf Hallo", "Antwort auf 2"]
    assert len(llm.messages) == 2


def test_terminal_session_stops_at_end_of_input() -> None:
    def end_of_input(prompt: str) -> str:
        raise EOFError

    session = TerminalSession(
        Agent(llm=EchoChatModel(), tools=create_tools()),
        input_reader=end_of_input,
    )

    asyncio.run(session.run())
