import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from gateway.features.conversation.application import (
    AgentEvent,
    AgentRunner,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
)
from gateway.features.conversation.domain import (
    SessionNotFoundError,
    SessionRepository,
    UserMessage,
)

_TOOL_KEYWORD = "tool"


class EchoAgentRunner(AgentRunner):
    """Streams the last user message back, so clients can be tested without an LLM.

    A message containing "tool" also emits a demo tool call round trip.
    """

    def __init__(self, sessions: SessionRepository, delta_delay: float = 0.05) -> None:
        self._sessions = sessions
        self._delta_delay = delta_delay

    async def run(
        self,
        session_id: UUID,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentEvent]:
        del metadata
        message = await self._last_user_message(session_id)

        if _TOOL_KEYWORD in message.lower():
            call_id = str(uuid4())
            yield ToolCallStarted(call_id, "echo_clock", {"session": str(session_id)})
            await asyncio.sleep(self._delta_delay)
            yield ToolCallCompleted(call_id, "echo_clock", {"ticks": len(message)})

        reply = f"echo: {message}"
        for chunk in _chunks(reply):
            await asyncio.sleep(self._delta_delay)
            yield ChatDelta(chunk)
        yield ChatCompleted(reply)

    async def _last_user_message(self, session_id: UUID) -> str:
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        for entry in reversed(session.entries):
            if isinstance(entry, UserMessage):
                return entry.content
        return ""


def _chunks(text: str) -> list[str]:
    words = text.split(" ")
    return [word if index == 0 else f" {word}" for index, word in enumerate(words)]
