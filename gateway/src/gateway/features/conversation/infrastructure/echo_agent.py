from collections.abc import AsyncIterator

from gateway.features.conversation.application import AgentRunner
from gateway.features.conversation.domain import (
    AgentOutput,
    ChatCompleted,
    ChatDelta,
    Session,
)


class EchoAgentRunner(AgentRunner):
    async def stream(
        self,
        session: Session,
        text: str,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentOutput]:
        del session, metadata
        yield ChatDelta(text=text)
        yield ChatCompleted(text=text)
