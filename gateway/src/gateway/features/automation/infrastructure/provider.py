from collections.abc import AsyncIterator
from uuid import UUID

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.features.automation.application import (
    AutomationActionExecutor,
    AutomationExecution,
    AutomationScheduler,
    AutomationService,
    AutomationTargetResolver,
)
from gateway.features.automation.domain import AutomationRepository
from gateway.features.automation.infrastructure.conversation import (
    ConversationAutomationActionExecutor,
    ConversationAutomationTargetResolver,
)
from gateway.features.automation.infrastructure.repository import (
    SQLAutomationRepository,
)
from gateway.features.automation.infrastructure.scheduling import (
    AutomationJobRunner,
    InProcessAutomationScheduler,
)
from gateway.features.conversation.application import SessionService, TurnService
from scheduler import Scheduler


class AutomationProvider(Provider):
    scope = Scope.APP

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
    def repository(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> AutomationRepository:
        return SQLAutomationRepository(session_factory)

    @provide
    def execution(
        self,
        repository: AutomationRepository,
        executor: AutomationActionExecutor,
    ) -> AutomationExecution:
        return AutomationExecution(repository, executor)

    @provide
    async def scheduler(
        self,
        execution: AutomationExecution,
    ) -> AsyncIterator[Scheduler[UUID]]:
        scheduler = Scheduler(AutomationJobRunner(execution))
        await scheduler.start()
        try:
            yield scheduler
        finally:
            await scheduler.stop()

    @provide
    def automation_scheduler(
        self,
        scheduler: Scheduler[UUID],
    ) -> AutomationScheduler:
        return InProcessAutomationScheduler(scheduler)

    @provide
    async def service(
        self,
        repository: AutomationRepository,
        targets: AutomationTargetResolver,
        scheduler: AutomationScheduler,
    ) -> AutomationService:
        service = AutomationService(repository, targets, scheduler)
        await service.resume()
        return service
