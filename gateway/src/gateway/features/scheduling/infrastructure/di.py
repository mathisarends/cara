from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.features.scheduling.infrastructure.persistence import SQLiteJobStore
from scheduler import JobStore


class SchedulingProvider(Provider):
    scope = Scope.APP

    @provide
    def job_store(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> JobStore:
        return SQLiteJobStore(session_factory)
