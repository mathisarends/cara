from collections.abc import AsyncIterator
from zoneinfo import ZoneInfo

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent.configuration import AgentSettings
from gateway.features.alarm.application import (
    AlarmExecution,
    AlarmRunExecutor,
    AlarmScheduler,
    AlarmService,
    AlarmStore,
    AlarmTargetResolver,
    Clock,
)
from gateway.features.alarm.domain import AlarmRepository
from gateway.features.alarm.infrastructure.conversation import (
    ConversationAlarmRunExecutor,
    ConversationAlarmTargetResolver,
)
from gateway.features.alarm.infrastructure.repository import SQLAlarmRepository
from gateway.features.alarm.infrastructure.scheduling import (
    InProcessAlarmScheduler,
    SystemClock,
)
from gateway.features.conversation.application import SessionService, TurnService


class AlarmProvider(Provider):
    scope = Scope.APP

    @provide
    def clock(self) -> Clock:
        return SystemClock()

    @provide
    def target_resolver(self, sessions: SessionService) -> AlarmTargetResolver:
        return ConversationAlarmTargetResolver(sessions)

    @provide
    def run_executor(
        self,
        turns: TurnService,
        settings: AgentSettings,
    ) -> AlarmRunExecutor:
        return ConversationAlarmRunExecutor(turns, ZoneInfo(settings.timezone))

    @provide
    def repository(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> AlarmRepository:
        return SQLAlarmRepository(session_factory)

    @provide
    def in_process_scheduler(self) -> InProcessAlarmScheduler:
        return InProcessAlarmScheduler()

    @provide
    def scheduler(self, scheduler: InProcessAlarmScheduler) -> AlarmScheduler:
        return scheduler

    @provide
    def store(
        self,
        repository: AlarmRepository,
        scheduler: AlarmScheduler,
    ) -> AlarmStore:
        return AlarmStore(repository, scheduler)

    @provide
    def execution(
        self,
        store: AlarmStore,
        executor: AlarmRunExecutor,
        clock: Clock,
    ) -> AlarmExecution:
        return AlarmExecution(store, executor, clock)

    @provide
    async def service(
        self,
        store: AlarmStore,
        targets: AlarmTargetResolver,
        clock: Clock,
        execution: AlarmExecution,
        scheduler: InProcessAlarmScheduler,
    ) -> AsyncIterator[AlarmService]:
        service = AlarmService(store, targets, clock)
        await service.resume()
        # The scheduler runs due alarms through the execution, which re-arms
        # through the scheduler, so it only starts once both exist.
        await scheduler.start(execution)
        try:
            yield service
        finally:
            await scheduler.stop()
