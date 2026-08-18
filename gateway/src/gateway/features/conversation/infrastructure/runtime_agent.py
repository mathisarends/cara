from uuid import UUID

from gateway.features.conversation.application import AgentEventBus, AgentRunner


class RuntimeAgentRunner(AgentRunner):
    """Placeholder until the gateway is connected to the current agent API."""

    async def run(
        self,
        session_id: UUID,
        metadata: dict[str, object],
        event_bus: AgentEventBus,
    ) -> None:
        del session_id, metadata, event_bus
        raise NotImplementedError("The gateway agent runtime is not configured.")
