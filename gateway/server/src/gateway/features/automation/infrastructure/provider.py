from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from pydantic_settings import BaseSettings, SettingsConfigDict

from gateway.features.automation.application import (
    AutomationActionExecutor,
    AutomationTargetResolver,
    SessionAutomationService,
)
from gateway.features.automation.domain import AutomationRepository
from gateway.features.automation.infrastructure.codec import (
    AutomationRecord,
    AutomationRecordCodec,
)
from gateway.features.automation.infrastructure.runner import (
    ConversationAutomationActionExecutor,
    ConversationAutomationTargetResolver,
    SchedulerAutomationRunner,
)
from gateway.features.automation.infrastructure.scheduler_repository import (
    SchedulerAutomationRepository,
)
from gateway.features.conversation.application import SessionService, TurnService
from scheduler import Scheduler, SqliteJobStore


class SchedulerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    scheduler_database: str = "./scheduler.sqlite3"


class AutomationProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> SchedulerSettings:
        return SchedulerSettings()

    @provide
    def target_resolver(
        self,
        sessions: SessionService,
    ) -> AutomationTargetResolver:
        return ConversationAutomationTargetResolver(sessions)

    @provide
    def action_executor(
        self,
        turns: TurnService,
    ) -> AutomationActionExecutor:
        return ConversationAutomationActionExecutor(turns)

    @provide
    async def scheduler(
        self,
        settings: SchedulerSettings,
        executor: AutomationActionExecutor,
    ) -> AsyncIterator[Scheduler[AutomationRecord]]:
        store = SqliteJobStore[AutomationRecord](
            settings.scheduler_database,
            payload_codec=AutomationRecordCodec(),
        )
        scheduler = Scheduler(runner=SchedulerAutomationRunner(executor), store=store)
        await scheduler.start()
        try:
            yield scheduler
        finally:
            await scheduler.stop()

    @provide
    def repository(
        self,
        scheduler: Scheduler[AutomationRecord],
    ) -> AutomationRepository:
        return SchedulerAutomationRepository(scheduler)

    @provide
    def service(
        self,
        repository: AutomationRepository,
        targets: AutomationTargetResolver,
    ) -> SessionAutomationService:
        return SessionAutomationService(repository, targets)
