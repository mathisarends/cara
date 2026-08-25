from datetime import timedelta
from zoneinfo import ZoneInfo

from gateway.features.automation.domain import AutomationEnvelope, ReminderPayload
from gateway.features.automation.presentation.schemas import (
    AtSchedule,
    AutomationResponse,
    AutomationSchedule,
    CronSchedule,
    IntervalSchedule,
    ReminderAutomationPayload,
    SessionAutomationTargetResponse,
)
from scheduler import At, Cron, Interval, ScheduledJob, Trigger


def automation_response(
    job: ScheduledJob[AutomationEnvelope],
) -> AutomationResponse:
    return AutomationResponse(
        id=job.id,
        name=job.name,
        created_at=job.created_at,
        next_run_at=job.next_run_at,
        schedule=_schedule(job),
        schema_version=job.payload.schema_version,
        target=SessionAutomationTargetResponse(
            kind=job.payload.target.kind,
            session_id=job.payload.target.session_id,
        ),
        payload=ReminderAutomationPayload(
            kind=job.payload.payload.kind,
            message=job.payload.payload.message,
            created_from_turn_id=job.payload.payload.created_from_turn_id,
        ),
    )


def automation_trigger(schedule: AutomationSchedule) -> Trigger:
    match schedule:
        case AtSchedule(run_at=run_at):
            return At(when=run_at)
        case IntervalSchedule(
            every_seconds=every_seconds,
            run_immediately=run_immediately,
        ):
            return Interval(
                every=timedelta(seconds=every_seconds),
                run_immediately=run_immediately,
            )
        case CronSchedule(expression=expression, timezone=timezone):
            return Cron(expression=expression, timezone=ZoneInfo(timezone))


def reminder_payload(payload: ReminderAutomationPayload) -> ReminderPayload:
    return ReminderPayload(
        kind=payload.kind,
        message=payload.message,
        created_from_turn_id=payload.created_from_turn_id,
    )


def _schedule(job: ScheduledJob[AutomationEnvelope]) -> AutomationSchedule:
    match job.trigger:
        case At(when=when):
            return AtSchedule(run_at=when)
        case Interval(every=every, run_immediately=run_immediately):
            return IntervalSchedule(
                every_seconds=every.total_seconds(),
                run_immediately=run_immediately,
            )
        case Cron(expression=expression, timezone=timezone):
            timezone_name = timezone.key if isinstance(timezone, ZoneInfo) else "UTC"
            return CronSchedule(expression=expression, timezone=timezone_name)
