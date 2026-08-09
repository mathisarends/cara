from collections.abc import AsyncIterator

from gateway.application import (
    AgentOutput,
    AgentRunner,
    ChatCompleted,
    ChatDelta,
    Session,
)


class EchoAgentRunner(AgentRunner):
    """Small runnable adapter until the real Cara agent is wired in."""

    async def stream(
        self,
        session: Session,
        text: str,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentOutput]:
        del session, metadata
        yield ChatDelta(text=text)
        yield ChatCompleted(text=text)
