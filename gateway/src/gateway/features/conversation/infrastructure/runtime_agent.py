from collections.abc import AsyncIterator

from cara_agent_plugin_api import AgentEvent, AgentRunner, AgentRunRequest


class RuntimeAgentRunner(AgentRunner):
    """Placeholder until the gateway is connected to the current agent API."""

    def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        del request
        raise NotImplementedError("The gateway agent runtime is not configured.")

    async def close(self) -> None:
        pass
