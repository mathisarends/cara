from uuid import UUID

from agent_plugin_api import AgentContext, AgentPluginContext
from gateway.features.conversation.infrastructure.echo_agent import (
    EchoAgentPlugin,
    EchoAgentRunner,
)


class _SessionReader:
    async def context_for_turn(
        self,
        session_id: UUID,
        input_id: UUID,
    ) -> AgentContext:
        del session_id, input_id
        return AgentContext(())


def test_echo_plugin_builds_a_runner_from_its_configuration() -> None:
    runner = EchoAgentPlugin().create(
        {"delta_delay": 0},
        AgentPluginContext(sessions=_SessionReader()),
    )

    assert isinstance(runner, EchoAgentRunner)
