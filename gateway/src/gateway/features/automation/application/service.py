from uuid import UUID

from gateway.features.automation.domain import (
    AutomationEnvelope,
    AutomationNotFoundError,
)
from scheduler import ScheduledJob, Scheduler


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
