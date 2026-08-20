import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

from cara_agent_plugin_api import (
    AgentEvent,
    AgentRunner,
    AgentRunRequest,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
)

_TOOL_KEYWORD = "tool"


class EchoAgentRunner(AgentRunner):
    """Streams the last user message back, so clients can be tested without an LLM.

    A message containing "tool" also emits a demo tool call round trip.
    """

    def __init__(self, delta_delay: float = 0.05) -> None:
        self._delta_delay = delta_delay

    async def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        message = request.input

        if _TOOL_KEYWORD in message.lower():
            call_id = str(uuid4())
            yield ToolCallStarted(
                call_id,
                "echo_clock",
                {"session": str(request.session.id)},
            )
            await asyncio.sleep(self._delta_delay)
            yield ToolCallCompleted(call_id, "echo_clock", {"ticks": len(message)})

        reply = f"echo: {message}"
        for chunk in _chunks(reply):
            await asyncio.sleep(self._delta_delay)
            yield ChatDelta(chunk)
        yield ChatCompleted(reply)

    async def close(self) -> None:
        pass


def _chunks(text: str) -> list[str]:
    words = text.split(" ")
    return [word if index == 0 else f" {word}" for index, word in enumerate(words)]
