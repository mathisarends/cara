from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest
from dishka import Provider, Scope, make_async_container, provide

from agent_plugin_api import (
    AGENT_PLUGIN_API_VERSION,
    AgentContext,
    AgentPluginContext,
    AgentRunner,
    AgentRunRequest,
    AgentSessionReader,
)
from gateway.agent_plugins import AgentPluginProvider


class _SessionReader:
    async def context_for_turn(self, session_id, input_id) -> AgentContext:
        del session_id, input_id
        return AgentContext(())


class _Runner:
    def __init__(self) -> None:
        self.closed = False

    async def run(self, request: AgentRunRequest) -> AsyncIterator:
        del request
        return
        yield

    async def close(self) -> None:
        self.closed = True


class _Plugin:
    api_version = AGENT_PLUGIN_API_VERSION

    def __init__(self, runner: _Runner) -> None:
        self._runner = runner

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> AgentRunner:
        del config, context
        return self._runner


class _TestProvider(Provider):
    scope = Scope.APP

    @provide
    def sessions(self) -> AgentSessionReader:
        return _SessionReader()


async def test_provider_closes_the_plugin_runner_on_container_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner()
    plugin = _Plugin(runner)
    monkeypatch.setattr(
        "gateway.agent_plugins.di.load_agent_plugin",
        lambda _: plugin,
    )
    monkeypatch.setenv("CARA_AGENT_CONFIG", "{}")
    container = make_async_container(AgentPluginProvider(), _TestProvider())

    resolved = await container.get(AgentRunner)
    assert resolved is runner
    assert not runner.closed

    await container.close()

    assert runner.closed
