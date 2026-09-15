from gateway.features.automation.application.ports import AutomationTargetResolver
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
    ) -> None:
        self._repository = repository
        self._targets = targets

    async def list(self, owner_id: str) -> tuple[Automation, ...]:
        return await self._repository.list_for_owner(owner_id)

    async def get(self, automation_id: str, owner_id: str) -> Automation:
        automation = await self._repository.get(automation_id)
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
            name=name,
        )
        return await self._repository.save(automation)

    async def update(
        self,
        automation_id: str,
        owner_id: str,
        *,
        schedule: AutomationSchedule,
        action: PromptAction,
        origin: AutomationOrigin,
        name: str | None = None,
    ) -> Automation:
        automation = await self.get(automation_id, owner_id)
        automation.update(
            schedule=schedule,
            action=action,
            origin=origin,
            name=name,
        )
        return await self._repository.save(automation)

    async def delete(self, automation_id: str, owner_id: str) -> None:
        automation = await self.get(automation_id, owner_id)
        await self._repository.remove(automation)
