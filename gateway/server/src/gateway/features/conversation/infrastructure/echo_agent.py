import asyncio
import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import UUID

from agent_plugin_api import (
    AGENT_PLUGIN_API_VERSION,
    AgentEvent,
    AgentPlugin,
    AgentPluginContext,
    AgentRunner,
    AgentRunRequest,
    AgentSessionRef,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnSteered,
)

_TOOL_KEYWORD = "tool"
# The demo tool runs far longer than a delta so there is a window to steer in.
_TOOL_DELAY_FACTOR = 60


class EchoAgentRunner(AgentRunner):
    """Streams the last user message back, so clients can be tested without an LLM.

    A message containing "tool" also emits a demo tool call round trip, whose
    deliberately slow run is the window in which steering can be exercised.
    """

    def __init__(self, delta_delay: float = 0.05) -> None:
        self._delta_delay = delta_delay
        self._steering: dict[UUID, list[str]] = {}

    async def prepare(self, session: AgentSessionRef) -> None:
        pass

    async def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        message = request.input

        if _TOOL_KEYWORD in message.lower():
            call_id = str(uuid.uuid4())
            yield ToolCallStarted(
                call_id,
                "echo_clock",
                {"session": str(request.session.id)},
            )
            await asyncio.sleep(self._delta_delay * _TOOL_DELAY_FACTOR)
            yield ToolCallCompleted(call_id, "echo_clock", {"ticks": len(message)})
            for steered in self._steering.pop(request.session.id, []):
                yield TurnSteered(steered)
                message = f"{message} + {steered}"

        reply = f"echo: {message}"
        for chunk in _chunks(reply):
            await asyncio.sleep(self._delta_delay)
            yield ChatDelta(chunk)
        yield ChatCompleted(reply)

    async def steer(self, session: AgentSessionRef, text: str) -> None:
        self._steering.setdefault(session.id, []).append(text)

    async def finish(self, session: AgentSessionRef) -> None:
        self._steering.pop(session.id, None)

    async def close(self) -> None:
        pass


def _chunks(text: str) -> list[str]:
    words = text.split(" ")
    return [word if index == 0 else f" {word}" for index, word in enumerate(words)]


class _EchoAgentPlugin:
    api_version = AGENT_PLUGIN_API_VERSION

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> AgentRunner:
        del context
        unknown = set(config) - {"delta_delay"}
        if unknown:
            fields = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown echo plugin configuration: {fields}")
        delta_delay = config.get("delta_delay", 0.05)
        if isinstance(delta_delay, bool) or not isinstance(delta_delay, (int, float)):
            raise TypeError("echo delta_delay must be a number")
        if delta_delay < 0:
            raise ValueError("echo delta_delay must not be negative")
        return EchoAgentRunner(float(delta_delay))


def create_plugin() -> AgentPlugin:
    return _EchoAgentPlugin()
