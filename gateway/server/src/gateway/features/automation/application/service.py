from dataclasses import replace
from uuid import UUID

from gateway.features.automation.domain import (
    AutomationEnvelope,
    AutomationNotFoundError,
    ReminderPayload,
    SessionAutomationTarget,
)
from scheduler import ScheduledJob, Scheduler, Trigger


class AutomationService:
    def __init__(self, scheduler: Scheduler[AutomationEnvelope]) -> None:
        self._scheduler = scheduler

    async def list_for_session(
        self,
        session_id: UUID,
    ) -> tuple[ScheduledJob[AutomationEnvelope], ...]:
        jobs = await self._scheduler.list()
        return tuple(job for job in jobs if job.payload.target.session_id == session_id)

    async def get_for_session(
        self,
        automation_id: str,
        session_id: UUID,
    ) -> ScheduledJob[AutomationEnvelope]:
        job = await self._scheduler.get(automation_id)
        if job is None or job.payload.target.session_id != session_id:
            raise AutomationNotFoundError(automation_id)
        return job

    async def create_for_session(
        self,
        session_id: UUID,
        *,
        trigger: Trigger,
        payload: ReminderPayload,
        name: str | None = None,
    ) -> ScheduledJob[AutomationEnvelope]:
        return await self._scheduler.schedule(
            trigger=trigger,
            payload=AutomationEnvelope(
                schema_version=1,
                target=SessionAutomationTarget(kind="session", session_id=session_id),
                payload=payload,
            ),
            name=name,
        )

    async def update_for_session(
        self,
        automation_id: str,
        session_id: UUID,
        *,
        trigger: Trigger,
        payload: ReminderPayload,
        name: str | None = None,
    ) -> ScheduledJob[AutomationEnvelope]:
        existing = await self.get_for_session(automation_id, session_id)
        job = await self._scheduler.update(
            automation_id,
            trigger=trigger,
            payload=replace(existing.payload, payload=payload),
            name=name,
        )
        if job is None:
            raise AutomationNotFoundError(automation_id)
        return job

    async def delete_for_session(
        self,
        automation_id: str,
        session_id: UUID,
    ) -> None:
        await self.get_for_session(automation_id, session_id)
        if not await self._scheduler.remove(automation_id):
            raise AutomationNotFoundError(automation_id)
