from datetime import timedelta

from gateway.features.automation.domain import (
    AtSchedule as DomainAtSchedule,
)
from gateway.features.automation.domain import (
    Automation,
    AutomationOrigin,
    PromptAction,
)
from gateway.features.automation.domain import (
    AutomationSchedule as DomainAutomationSchedule,
)
from gateway.features.automation.domain import (
    CronSchedule as DomainCronSchedule,
)
from gateway.features.automation.domain import (
    IntervalSchedule as DomainIntervalSchedule,
)
from gateway.features.automation.presentation.rpc.schemas import (
    AtSchedule,
    AutomationResponse,
    AutomationSchedule,
    CronSchedule,
    IntervalSchedule,
    ReminderAutomationPayload,
    SessionAutomationTargetResponse,
)


def automation_response(automation: Automation) -> AutomationResponse:
    if automation.next_run_at is None:
        raise ValueError(f"Automation {automation.id!r} has not been scheduled")
    return AutomationResponse(
        id=automation.id,
        name=automation.name,
        created_at=automation.created_at,
        next_run_at=automation.next_run_at,
        schedule=schedule_response(automation.schedule),
        target=SessionAutomationTargetResponse(
            kind="session",
            session_id=automation.target.session_id,
        ),
        payload=ReminderAutomationPayload(
            kind="reminder",
            instruction=automation.action.instruction,
            created_from_turn_id=automation.origin.created_from_turn_id,
        ),
    )


def automation_schedule(schedule: AutomationSchedule) -> DomainAutomationSchedule:
    match schedule:
        case AtSchedule(run_at=run_at):
            return DomainAtSchedule(run_at=run_at)
        case IntervalSchedule(
            every_seconds=every_seconds,
            run_immediately=run_immediately,
        ):
            return DomainIntervalSchedule(
                every=timedelta(seconds=every_seconds),
                run_immediately=run_immediately,
            )
        case CronSchedule(expression=expression, timezone=timezone):
            return DomainCronSchedule(expression=expression, timezone=timezone)


def prompt_action(payload: ReminderAutomationPayload) -> PromptAction:
    return PromptAction(payload.instruction)


def automation_origin(payload: ReminderAutomationPayload) -> AutomationOrigin:
    return AutomationOrigin(payload.created_from_turn_id)


def schedule_response(schedule: DomainAutomationSchedule) -> AutomationSchedule:
    match schedule:
        case DomainAtSchedule(run_at=run_at):
            return AtSchedule(run_at=run_at)
        case DomainIntervalSchedule(every=every, run_immediately=run_immediately):
            return IntervalSchedule(
                every_seconds=every.total_seconds(),
                run_immediately=run_immediately,
            )
        case DomainCronSchedule(expression=expression, timezone=timezone):
            return CronSchedule(expression=expression, timezone=timezone)
