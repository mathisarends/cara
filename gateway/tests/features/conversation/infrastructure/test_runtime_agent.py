from uuid import uuid4

import pytest

from cara_agent_plugin_api import AgentChannelRef, AgentRunRequest, AgentSessionRef
from gateway.features.conversation.infrastructure import RuntimeAgentRunner


def test_runtime_agent_is_an_explicit_placeholder() -> None:
    runner = RuntimeAgentRunner()

    with pytest.raises(
        NotImplementedError,
        match="gateway agent runtime is not configured",
    ):
        runner.run(
            AgentRunRequest(
                session=AgentSessionRef(uuid4(), AgentChannelRef("test")),
                turn_id=uuid4(),
                input_id=uuid4(),
                input="hello",
            )
        )
