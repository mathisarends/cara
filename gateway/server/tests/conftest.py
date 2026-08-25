from collections.abc import Mapping
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_plugin_api import AgentPluginContext, AgentRunner
from gateway.app import create_app
from gateway.features.conversation.infrastructure import EchoAgentRunner


class _TestAgentPlugin:
    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> AgentRunner:
        del config, context
        return EchoAgentRunner(delta_delay=0)


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(
        "gateway.agent_plugins.di.load_agent_plugin",
        lambda _: _TestAgentPlugin(),
    )
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
