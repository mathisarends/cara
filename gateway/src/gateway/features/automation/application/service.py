from uuid import UUID

from gateway.features.automation.application.ports import (
    AutomationScheduler,
    AutomationTargetResolver,
)
from gateway.features.automation.domain import (
    Automation,
    AutomationNotFoundError,
    AutomationOrigin,
    AutomationRepository,
    AutomationSchedule,
    AutomationTarget,
    PromptAction,
)


class AutomationService:
    def __init__(
        self,
        repository: AutomationRepository,
        targets: AutomationTargetResolver,
        scheduler: AutomationScheduler,
    ) -> None:
        self._repository = repository
        self._targets = targets
        self._scheduler = scheduler

    async def list(self, owner_id: str) -> tuple[Automation, ...]:
        return await self._repository.find_by_owner(owner_id)

    async def get(self, automation_id: UUID, owner_id: str) -> Automation:
        automation = await self._repository.find_by_id(automation_id)
        if automation is None:
            raise AutomationNotFoundError(automation_id)
        automation.require_owner(owner_id)
        return automation

    async def create(
        self,
        owner_id: str,
        *,
        target: AutomationTarget,
        schedule: AutomationSchedule,
        action: PromptAction,
        origin: AutomationOrigin,
        name: str | None = None,
    ) -> Automation:
        await self._targets.require(target)
        automation = Automation.create(
            owner_id=owner_id,
            target=target,
            schedule=schedule,
            action=action,
            origin=origin,
            next_run_at=self._scheduler.first_run_at(schedule),
            name=name,
        )
        return await self._save_and_arm(automation)

    async def update(
        self,
        automation_id: UUID,
        owner_id: str,
        *,
        schedule: AutomationSchedule,
        action: PromptAction,
        origin: AutomationOrigin,
        name: str | None = None,
    ) -> Automation:
        automation = await self.get(automation_id, owner_id)
        self._scheduler.disarm(automation)
        automation.update(
            schedule=schedule,
            action=action,
            origin=origin,
            name=name,
            next_run_at=self._scheduler.first_run_at(schedule),
        )
        return await self._save_and_arm(automation)

    async def delete(self, automation_id: UUID, owner_id: str) -> None:
        automation = await self.get(automation_id, owner_id)
        self._scheduler.disarm(automation)
        await self._repository.remove(automation)

    async def resume(self) -> None:
        for automation in await self._repository.find_all():
            self._scheduler.arm(automation)

    async def _save_and_arm(self, automation: Automation) -> Automation:
        # Persist before arming so a due run always finds the stored automation.
        saved = await self._repository.save(automation)
        self._scheduler.arm(saved)
        return saved
