from datetime import datetime
from uuid import UUID

from gateway.features.automation.application.ports import AutomationActionExecutor
from gateway.features.automation.domain import Automation, AutomationRepository


class AutomationExecution:
    def __init__(
        self,
        repository: AutomationRepository,
        executor: AutomationActionExecutor,
    ) -> None:
        self._repository = repository
        self._executor = executor

    async def run(
        self,
        automation_id: UUID,
        *,
        scheduled_for: datetime,
        next_run_at: datetime | None,
    ) -> None:
        automation = await self._repository.find_by_id(automation_id)
        if automation is None:
            return
        try:
            await self._executor.execute(
                automation.id,
                automation.target,
                automation.action,
                automation.delivery,
                scheduled_for,
            )
        except Exception:
            # The scheduler advances past failed runs, so persistence must too.
            await self._advance(automation, next_run_at)
            raise
        await self._advance(automation, next_run_at)

    async def _advance(
        self,
        automation: Automation,
        next_run_at: datetime | None,
    ) -> None:
        if next_run_at is None:
            await self._repository.remove(automation)
            return
        automation.reschedule(next_run_at)
        await self._repository.save(automation)
