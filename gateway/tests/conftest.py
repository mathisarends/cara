import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.features.conversation.infrastructure.echo_agent import plugin


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(
        "gateway.agent_plugins.di.load_agent_plugin",
        lambda _: plugin,
    )
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
