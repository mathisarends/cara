from collections.abc import AsyncIterator
from uuid import UUID

from gateway.features.conversation.application import AgentEvent, AgentRunner


class RuntimeAgentRunner(AgentRunner):
    """Placeholder until the gateway is connected to the current agent API."""

    def run(
        self,
        session_id: UUID,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentEvent]:
        del session_id, metadata
        raise NotImplementedError("The gateway agent runtime is not configured.")
