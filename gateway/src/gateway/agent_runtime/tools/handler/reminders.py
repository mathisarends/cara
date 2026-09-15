from datetime import timedelta
from uuid import UUID

from agent.tools.middleware import ToolError
from gateway.agent_runtime.tools.handler.ports import (
    Reminder,
    Reminders,
    ReminderSchedule,
    RemindEvery,
    RemindOnce,
    RemindOnCron,
)
from gateway.features.automation.application import AutomationService
from gateway.features.automation.domain import (
    AtSchedule,
    Automation,
    AutomationNotFoundError,
    AutomationSchedule,
    ChannelTarget,
    CronSchedule,
    IntervalSchedule,
    PromptAction,
    SessionTarget,
)
from gateway.features.conversation.domain import SessionNotFoundError
from gateway.shared import UnitOfWork


class GatewayReminders(Reminders):
    """Turn-bound reminder tools backed directly by gateway use cases."""

    def __init__(
        self,
        automations: UnitOfWork[AutomationService],
        *,
        owner_id: str,
        session_id: UUID,
        channel: str,
        channel_scoped: bool,
    ) -> None:
        self._automations = automations
        self._owner_id = owner_id
        self._session_id = session_id
        self._channel = channel
        self._channel_scoped = channel_scoped

    async def list(self) -> tuple[Reminder, ...]:
        async with self._automations() as service:
            automations = await service.list(self._owner_id)
        return tuple(_reminder(automation) for automation in automations)

    async def create(
        self,
        *,
        instruction: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder:
        try:
            async with self._automations() as service:
                target = (
                    ChannelTarget(self._channel)
                    if self._channel_scoped
                    else SessionTarget(self._session_id)
                )
                automation = await service.create(
                    self._owner_id,
                    target=target,
                    schedule=_automation_schedule(schedule),
                    action=PromptAction(instruction),
                    name=name,
                )
        except (SessionNotFoundError, ValueError) as error:
            raise ToolError(str(error)) from None
        return _reminder(automation)

    async def update(
        self,
        reminder_id: UUID,
        *,
        instruction: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder:
        try:
            async with self._automations() as service:
                automation = await service.update(
                    reminder_id,
                    self._owner_id,
                    schedule=_automation_schedule(schedule),
                    action=PromptAction(instruction),
                    name=name,
                )
        except (AutomationNotFoundError, ValueError) as error:
            raise ToolError(str(error)) from None
        return _reminder(automation)

    async def delete(self, reminder_id: UUID) -> None:
        try:
            async with self._automations() as service:
                await service.delete(reminder_id, self._owner_id)
        except AutomationNotFoundError as error:
            raise ToolError(str(error)) from None


def _reminder(automation: Automation) -> Reminder:
    return Reminder(
        id=automation.id,
        instruction=automation.action.instruction,
        schedule=_reminder_schedule(automation.schedule),
        next_run_at=automation.next_run_at,
        name=automation.name,
    )


def _reminder_schedule(schedule: AutomationSchedule) -> ReminderSchedule:
    match schedule:
        case AtSchedule(run_at=run_at):
            return RemindOnce(when=run_at)
        case IntervalSchedule(every=every):
            return RemindEvery(seconds=every.total_seconds())
        case CronSchedule(expression=expression, timezone=timezone):
            return RemindOnCron(expression=expression, timezone=timezone)


def _automation_schedule(schedule: ReminderSchedule) -> AutomationSchedule:
    match schedule:
        case RemindOnce(when=when):
            return AtSchedule(run_at=when)
        case RemindEvery(seconds=seconds):
            return IntervalSchedule(every=timedelta(seconds=seconds))
        case RemindOnCron(expression=expression, timezone=timezone):
            return CronSchedule(expression=expression, timezone=timezone)
