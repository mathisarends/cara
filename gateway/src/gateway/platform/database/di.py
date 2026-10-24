from collections.abc import AsyncGenerator, AsyncIterator

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from gateway.platform.database.settings import DatabaseSettings
from gateway.platform.database.transaction import DatabaseTransaction
from gateway.shared.transaction import Transaction


class DatabaseProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> DatabaseSettings:
        return DatabaseSettings()

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
    def database_transaction(self) -> DatabaseTransaction:
        return DatabaseTransaction()

    @provide(scope=Scope.REQUEST)
    def transaction(self, transaction: DatabaseTransaction) -> Transaction:
        return transaction

    @provide(scope=Scope.REQUEST)
    async def session(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        transaction: DatabaseTransaction,
    ) -> AsyncGenerator[AsyncSession, BaseException | None]:
        async with session_factory() as session:
            try:
                # Dishka sends the scope's exception into the generator.
                scope_error = yield session
                if scope_error is not None:
                    await session.rollback()
                    return
                await session.commit()
            except BaseException:
                await session.rollback()
                raise
            transaction.complete()
