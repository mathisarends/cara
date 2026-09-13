from uuid import UUID

from gateway.features.automation.application.ports import AutomationTargetResolver
from gateway.features.automation.domain import (
    Automation,
    AutomationNotFoundError,
    AutomationOrigin,
    AutomationRepository,
    AutomationSchedule,
    PromptAction,
    SessionTarget,
)


class SessionAutomationService:
    def __init__(
        self,
        repository: AutomationRepository,
        targets: AutomationTargetResolver,
    ) -> None:
        self._repository = repository
        self._targets = targets

    async def list(self, session_id: UUID) -> tuple[Automation, ...]:
        return await self._repository.list_for_session(session_id)

    async def get(self, automation_id: str, session_id: UUID) -> Automation:
        automation = await self._repository.get(automation_id)
        if automation is None:
            raise AutomationNotFoundError(automation_id)
        automation.require_session(session_id)
        return automation

    async def create(
        self,
        session_id: UUID,
        *,
        schedule: AutomationSchedule,
        action: PromptAction,
        origin: AutomationOrigin,
        name: str | None = None,
    ) -> Automation:
        await self._targets.require_session(session_id)
        automation = Automation.create_for_session(
            target=SessionTarget(session_id),
            schedule=schedule,
            action=action,
            origin=origin,
            name=name,
        )
        return await self._repository.save(automation)

    async def update(
        self,
        automation_id: str,
        session_id: UUID,
        *,
        schedule: AutomationSchedule,
        action: PromptAction,
        origin: AutomationOrigin,
        name: str | None = None,
    ) -> Automation:
        automation = await self.get(automation_id, session_id)
        automation.update(
            schedule=schedule,
            action=action,
            origin=origin,
            name=name,
        )
        return await self._repository.save(automation)

    async def delete(self, automation_id: str, session_id: UUID) -> None:
        automation = await self.get(automation_id, session_id)
        await self._repository.remove(automation)
