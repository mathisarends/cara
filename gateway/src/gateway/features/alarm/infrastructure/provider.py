from zoneinfo import ZoneInfo

from dishka import AsyncContainer, Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

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
    AlarmRuntime,
    InProcessAlarmScheduler,
    SystemClock,
)
from gateway.features.conversation.application import SessionService, TurnService
from gateway.features.voice.application import VoiceTurnService
from gateway.platform.database import ScopedUnitOfWork
from gateway.shared import UnitOfWork


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
        voice_turns: VoiceTurnService,
        settings: AgentSettings,
    ) -> AlarmRunExecutor:
        return ConversationAlarmRunExecutor(
            turns,
            voice_turns,
            ZoneInfo(settings.timezone),
        )

    @provide(scope=Scope.REQUEST)
    def repository(self, session: AsyncSession) -> AlarmRepository:
        return SQLAlarmRepository(session)

    @provide
    def repository_unit_of_work(
        self,
        container: AsyncContainer,
    ) -> UnitOfWork[AlarmRepository]:
        return ScopedUnitOfWork(container, AlarmRepository)

    @provide
    def in_process_scheduler(self) -> InProcessAlarmScheduler:
        return InProcessAlarmScheduler()

    @provide
    def scheduler(self, scheduler: InProcessAlarmScheduler) -> AlarmScheduler:
        return scheduler

    @provide
    def store(
        self,
        repositories: UnitOfWork[AlarmRepository],
        scheduler: AlarmScheduler,
    ) -> AlarmStore:
        return AlarmStore(repositories, scheduler)

    @provide
    def execution(
        self,
        store: AlarmStore,
        executor: AlarmRunExecutor,
        clock: Clock,
    ) -> AlarmExecution:
        return AlarmExecution(store, executor, clock)

    @provide
    def service(
        self,
        store: AlarmStore,
        targets: AlarmTargetResolver,
        clock: Clock,
    ) -> AlarmService:
        return AlarmService(store, targets, clock)

    @provide
    def runtime(
        self,
        service: AlarmService,
        execution: AlarmExecution,
        scheduler: InProcessAlarmScheduler,
    ) -> AlarmRuntime:
        return AlarmRuntime(service, execution, scheduler)
