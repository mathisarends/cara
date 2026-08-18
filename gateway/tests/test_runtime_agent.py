import asyncio
from uuid import uuid4

import pytest

from gateway.features.conversation.application import AgentEventBus
from gateway.features.conversation.infrastructure import RuntimeAgentRunner


def test_runtime_agent_is_an_explicit_placeholder() -> None:
    runner = RuntimeAgentRunner()

    with pytest.raises(
        NotImplementedError,
        match="gateway agent runtime is not configured",
    ):
        asyncio.run(runner.run(uuid4(), {}, AgentEventBus()))
