from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from gateway.infrastructure.database.settings import DatabaseSettings


class DatabaseProvider(Provider):
    scope = Scope.APP

    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self._settings = settings or DatabaseSettings()
        super().__init__()

    @provide
    def settings(self) -> DatabaseSettings:
        return self._settings

    @provide
    async def engine(self) -> AsyncIterator[AsyncEngine]:
        options = {"poolclass": StaticPool} if self._settings.is_in_memory else {}
        engine = create_async_engine(self._settings.async_url, **options)
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
