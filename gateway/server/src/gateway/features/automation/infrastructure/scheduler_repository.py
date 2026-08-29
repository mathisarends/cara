from uuid import UUID
from zoneinfo import ZoneInfo

from gateway.features.automation.domain import (
    AtSchedule,
    Automation,
    AutomationNotFoundError,
    AutomationOrigin,
    AutomationRepository,
    AutomationSchedule,
    CronSchedule,
    IntervalSchedule,
    PromptAction,
    SessionTarget,
)
from gateway.features.automation.infrastructure.codec import (
    AutomationRecord,
    PromptActionRecord,
    SessionTargetRecord,
)
from scheduler import At, Cron, Interval, ScheduledJob, Scheduler, Trigger


class SchedulerAutomationRepository(AutomationRepository):
    def __init__(self, scheduler: Scheduler[AutomationRecord]) -> None:
        self._scheduler = scheduler

    async def list_for_session(self, session_id: UUID) -> tuple[Automation, ...]:
        jobs = await self._scheduler.list()
        return tuple(
            _to_domain(job)
            for job in jobs
            if job.payload.target.session_id == session_id
        )

    async def get(self, automation_id: str) -> Automation | None:
        job = await self._scheduler.get(automation_id)
        return _to_domain(job) if job is not None else None

    async def save(self, automation: Automation) -> Automation:
        trigger = _to_trigger(automation.schedule)
        record = _to_record(automation)
        existing = await self._scheduler.get(automation.id)
        if existing is None:
            job = await self._scheduler.schedule(
                trigger=trigger,
                payload=record,
                job_id=automation.id,
                name=automation.name,
            )
        else:
            job = await self._scheduler.update(
                automation.id,
                trigger=trigger,
                payload=record,
                name=automation.name,
            )
            if job is None:
                raise AutomationNotFoundError(automation.id)
        return _to_domain(job)

    async def remove(self, automation: Automation) -> None:
        if not await self._scheduler.remove(automation.id):
            raise AutomationNotFoundError(automation.id)


def _to_domain(job: ScheduledJob[AutomationRecord]) -> Automation:
    return Automation(
        id=job.id,
        created_at=job.created_at,
        target=SessionTarget(job.payload.target.session_id),
        schedule=_to_schedule(job.trigger),
        action=PromptAction(job.payload.payload.instruction),
        origin=AutomationOrigin(job.payload.payload.created_from_turn_id),
        name=job.name,
        next_run_at=job.next_run_at,
    )


def _to_record(automation: Automation) -> AutomationRecord:
    return AutomationRecord(
        schema_version=2,
        target=SessionTargetRecord(
            kind="session",
            session_id=automation.target.session_id,
        ),
        payload=PromptActionRecord(
            kind="reminder",
            instruction=automation.action.instruction,
            created_from_turn_id=automation.origin.created_from_turn_id,
        ),
    )


def _to_trigger(schedule: AutomationSchedule) -> Trigger:
    match schedule:
        case AtSchedule(run_at=run_at):
            return At(when=run_at)
        case IntervalSchedule(every=every, run_immediately=run_immediately):
            return Interval(every=every, run_immediately=run_immediately)
        case CronSchedule(expression=expression, timezone=timezone):
            return Cron(expression=expression, timezone=ZoneInfo(timezone))


def _to_schedule(trigger: Trigger) -> AutomationSchedule:
    match trigger:
        case At(when=when):
            return AtSchedule(run_at=when)
        case Interval(every=every, run_immediately=run_immediately):
            return IntervalSchedule(
                every=every,
                run_immediately=run_immediately,
            )
        case Cron(expression=expression, timezone=timezone):
            timezone_name = timezone.key if isinstance(timezone, ZoneInfo) else "UTC"
            return CronSchedule(expression=expression, timezone=timezone_name)
