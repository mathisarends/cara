from collections.abc import AsyncIterator
from uuid import UUID

from gateway.features.conversation.application import AgentRunner
from gateway.features.conversation.domain import (
    AgentOutput,
    ChatCompleted,
    ChatDelta,
    SessionNotFoundError,
    SessionRepository,
    UserMessage,
)


class EchoAgentRunner(AgentRunner):
    def __init__(self, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def stream(
        self,
        session_id: UUID,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentOutput]:
        del metadata
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        text = next(
            entry.content
            for entry in reversed(session.entries)
            if isinstance(entry, UserMessage)
        )
        yield ChatDelta(text=text)
        yield ChatCompleted(text=text)
