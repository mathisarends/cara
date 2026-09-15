from uuid import UUID

from dishka import AsyncContainer, Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

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
    AutomationRuntime,
    InProcessAutomationScheduler,
)
from gateway.features.conversation.application import SessionService, TurnService
from gateway.platform.database import ScopedUnitOfWork
from gateway.shared.transaction import Transaction
from gateway.shared.unit_of_work import UnitOfWork
from scheduler import Scheduler


class AutomationProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def target_resolver(
        self,
        sessions: SessionService,
    ) -> AutomationTargetResolver:
        return ConversationAutomationTargetResolver(sessions)

    @provide(scope=Scope.APP)
    def action_executor(
        self,
        sessions: SessionService,
        turns: TurnService,
    ) -> AutomationActionExecutor:
        return ConversationAutomationActionExecutor(sessions, turns)

    @provide(scope=Scope.REQUEST)
    def repository(
        self,
        session: AsyncSession,
    ) -> AutomationRepository:
        return SQLAutomationRepository(session)

    @provide(scope=Scope.REQUEST)
    def execution(
        self,
        repository: AutomationRepository,
        executor: AutomationActionExecutor,
    ) -> AutomationExecution:
        return AutomationExecution(repository, executor)

    @provide(scope=Scope.APP)
    def execution_unit_of_work(
        self,
        container: AsyncContainer,
    ) -> UnitOfWork[AutomationExecution]:
        unit_of_work = ScopedUnitOfWork(container, AutomationExecution)
        return unit_of_work

    @provide(scope=Scope.APP)
    def scheduler(
        self,
        unit_of_work: UnitOfWork[AutomationExecution],
    ) -> Scheduler[UUID]:
        runner = AutomationJobRunner(unit_of_work)
        return Scheduler(runner)

    @provide(scope=Scope.APP)
    def automation_scheduler(
        self,
        scheduler: Scheduler[UUID],
    ) -> AutomationScheduler:
        return InProcessAutomationScheduler(scheduler)

    @provide(scope=Scope.REQUEST)
    def service(
        self,
        repository: AutomationRepository,
        targets: AutomationTargetResolver,
        scheduler: AutomationScheduler,
        transaction: Transaction,
    ) -> AutomationService:
        return AutomationService(repository, targets, scheduler, transaction)

    @provide(scope=Scope.APP)
    def service_unit_of_work(
        self,
        container: AsyncContainer,
    ) -> UnitOfWork[AutomationService]:
        unit_of_work = ScopedUnitOfWork(container, AutomationService)
        return unit_of_work

    @provide(scope=Scope.APP)
    def runtime(
        self,
        scheduler: Scheduler[UUID],
        unit_of_work: UnitOfWork[AutomationService],
    ) -> AutomationRuntime:
        return AutomationRuntime(scheduler, unit_of_work)
