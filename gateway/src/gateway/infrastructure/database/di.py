import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dishka import Provider, Scope, provide
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from gateway.infrastructure.database.migrations import run_migrations
from gateway.infrastructure.database.settings import DatabaseSettings

logger = logging.getLogger(__name__)


class DatabaseProvider(Provider):
    scope = Scope.APP

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        super().__init__()

    @provide
    def settings(self) -> DatabaseSettings:
        return self._settings

    @provide
    async def engine(
        self,
        settings: DatabaseSettings,
    ) -> AsyncIterator[AsyncEngine]:
        options = {"poolclass": StaticPool} if settings.is_in_memory else {}
        engine = create_async_engine(settings.async_url, **options)
        try:
            yield engine
        finally:
            await engine.dispose()

    @provide
    def session_factory(
        self,
        engine: AsyncEngine,
    ) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(engine, expire_on_commit=False)

    @provide(scope=Scope.REQUEST)
    async def session(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("%s starting up", app.title)
    engine = await app.state.dishka_container.get(AsyncEngine)
    await run_migrations(engine)
    try:
        yield
    finally:
        await app.state.dishka_container.close()
        logger.info("%s shutting down", app.title)
