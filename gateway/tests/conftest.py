import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from gateway.app import create_app
from gateway.features.conversation.application import (
    AgentEvent,
    AgentRunRequest,
    AgentSessionRef,
    ChatCompleted,
)
from gateway.platform.database.migrations import run_migrations

_TOKEN = "test-gateway-token-with-32-characters"


class _TestAgentRuntime:
    async def prepare(self, session: AgentSessionRef) -> None:
        del session

    async def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        yield ChatCompleted(request.input)

    async def steer(self, session: AgentSessionRef, text: str) -> None:
        del session, text

    async def finish(self, session: AgentSessionRef) -> None:
        del session

    async def close(self) -> None:
        pass


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FastAPI:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'gateway.sqlite3').as_posix()}"
    asyncio.run(_migrate(database_url))
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("CARA_GATEWAY_TOKEN", _TOKEN)
    monkeypatch.setattr(
        "gateway.agent_runtime.provider.CaraAgentRuntime",
        lambda *args: _TestAgentRuntime(),
    )
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app, headers={"Authorization": f"Bearer {_TOKEN}"}) as test_client:
        yield test_client


@pytest.fixture
def anonymous_client(app: FastAPI) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_engine() -> AsyncIterator[AsyncEngine]:
    # StaticPool keeps every connection on the same in-memory database; without
    # it, concurrent connections (e.g. a background turn task racing the test's
    # own queries) would each see a separate, table-less :memory: database.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(
    async_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False)


async def _migrate(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        await run_migrations(engine)
    finally:
        await engine.dispose()
