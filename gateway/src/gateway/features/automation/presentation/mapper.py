from collections.abc import Iterable
from datetime import timedelta

from gateway.features.automation import domain
from gateway.features.automation.presentation.schemas import (
    AtSchedule,
    AutomationListResponse,
    AutomationResponse,
    AutomationSchedule,
    AutomationTarget,
    CronSchedule,
    IntervalSchedule,
    ReminderPayload,
    SessionTarget,
)


def to_automation_list_response(
    automations: Iterable[domain.Automation],
) -> AutomationListResponse:
    return AutomationListResponse(
        automations=tuple(to_automation_response(item) for item in automations)
    )


def to_automation_response(automation: domain.Automation) -> AutomationResponse:
    return AutomationResponse(
        id=automation.id,
        owner_id=automation.owner_id,
        name=automation.name,
        created_at=automation.created_at,
        next_run_at=automation.next_run_at,
        schedule=_to_schedule_schema(automation.schedule),
        target=_to_target_schema(automation.target),
        payload=ReminderPayload(instruction=automation.action.instruction),
    )


def to_schedule(schedule: AutomationSchedule) -> domain.AutomationSchedule:
    match schedule:
        case AtSchedule(run_at=run_at):
            return domain.AtSchedule(run_at=run_at)
        case IntervalSchedule(
            every_seconds=every_seconds,
            run_immediately=run_immediately,
        ):
            return domain.IntervalSchedule(
                every=timedelta(seconds=every_seconds),
                run_immediately=run_immediately,
            )
        case CronSchedule(expression=expression, timezone=timezone):
            return domain.CronSchedule(expression=expression, timezone=timezone)


def to_target(target: AutomationTarget) -> domain.AutomationTarget:
    match target:
        case SessionTarget(session_id=session_id):
            return domain.SessionTarget(session_id)


def to_action(payload: ReminderPayload) -> domain.PromptAction:
    return domain.PromptAction(payload.instruction)


def _to_schedule_schema(schedule: domain.AutomationSchedule) -> AutomationSchedule:
    match schedule:
        case domain.AtSchedule(run_at=run_at):
            return AtSchedule(kind=domain.ScheduleKind.AT, run_at=run_at)
        case domain.IntervalSchedule(every=every, run_immediately=run_immediately):
            return IntervalSchedule(
                kind=domain.ScheduleKind.INTERVAL,
                every_seconds=every.total_seconds(),
                run_immediately=run_immediately,
            )
        case domain.CronSchedule(expression=expression, timezone=timezone):
            return CronSchedule(
                kind=domain.ScheduleKind.CRON,
                expression=expression,
                timezone=timezone,
            )


def _to_target_schema(target: domain.AutomationTarget) -> AutomationTarget:
    match target:
        case domain.SessionTarget(session_id=session_id):
            return SessionTarget(session_id=session_id)
