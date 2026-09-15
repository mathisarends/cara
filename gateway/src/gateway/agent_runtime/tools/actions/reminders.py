from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from agenttoolkit import Inject, Tools, provided
from pydantic import Field

from agent.clock import LocalClock
from agent.tools.middleware import ToolError
from agent.tools.params import ToolParams
from gateway.agent_runtime.tools.handler import (
    Reminder,
    Reminders,
    ReminderSchedule,
    RemindEvery,
    RemindOnce,
    RemindOnCron,
)


class _ReminderParams(ToolParams):
    run_at: datetime = Field(
        description="Future local wall-clock date and time.",
    )
    timezone: str | None = Field(
        default=None,
        description="IANA timezone; defaults to the configured local timezone.",
    )
    instruction: str = Field(
        description="Self-contained instruction for the future agent run."
    )
    name: str | None = Field(
        default=None,
        description="Optional short label.",
    )


class CreateReminderParams(_ReminderParams):
    pass


class UpdateReminderParams(_ReminderParams):
    reminder_id: UUID = Field(description="Reminder id from list_reminders.")


class DeleteReminderParams(ToolParams):
    reminder_id: UUID = Field(description="Reminder id from list_reminders.")


class ListRemindersParams(ToolParams):
    pass


def register_reminder_tools(tools: Tools) -> None:
    available = provided(Reminders)

    @tools.tool(
        description="List reminders for this conversation.",
        params=ListRemindersParams,
        available_when=available,
    )
    async def list_reminders(
        params: ListRemindersParams,
        reminders: Inject[Reminders],
    ) -> str:
        scheduled = await reminders.list()
        if not scheduled:
            return "No reminders are scheduled."
        return "\n".join(_render_reminder(reminder) for reminder in scheduled)

    @tools.tool(
        description="Schedule a one-time future agent run for this conversation.",
        params=CreateReminderParams,
        available_when=available,
    )
    async def create_reminder(
        params: CreateReminderParams,
        reminders: Inject[Reminders],
        clock: Inject[LocalClock],
    ) -> str:
        reminder = await reminders.create(
            instruction=params.instruction,
            schedule=_schedule(params, clock=clock),
            name=params.name,
        )
        return f"Scheduled: {_render_reminder(reminder)}"

    @tools.tool(
        description="Replace a reminder's time, instruction, and name.",
        params=UpdateReminderParams,
        available_when=available,
    )
    async def update_reminder(
        params: UpdateReminderParams,
        reminders: Inject[Reminders],
        clock: Inject[LocalClock],
    ) -> str:
        reminder = await reminders.update(
            params.reminder_id,
            instruction=params.instruction,
            schedule=_schedule(params, clock=clock),
            name=params.name,
        )
        return f"Updated: {_render_reminder(reminder)}"

    @tools.tool(
        description="Delete a reminder scheduled for this conversation.",
        params=DeleteReminderParams,
        available_when=available,
    )
    async def delete_reminder(
        params: DeleteReminderParams,
        reminders: Inject[Reminders],
    ) -> str:
        await reminders.delete(params.reminder_id)
        return f"Deleted reminder {params.reminder_id}."


def _schedule(params: _ReminderParams, *, clock: LocalClock) -> RemindOnce:
    timezone_name = params.timezone or clock.timezone
    timezone = _timezone(timezone_name)
    when = _localised(params.run_at, timezone)
    now = clock.now()
    if when.astimezone(UTC) <= now.astimezone(UTC):
        current_time = now.astimezone(timezone).isoformat(timespec="seconds")
        raise ToolError(
            "params.run_at must be in the future. "
            f"Current local time in {timezone.key} is {current_time}"
        )
    return RemindOnce(when=when)


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError) as error:
        raise ToolError(f"Unknown timezone '{name}'") from error


def _localised(when: datetime, timezone: ZoneInfo) -> datetime:
    return when if when.tzinfo is not None else when.replace(tzinfo=timezone)


def _render_reminder(reminder: Reminder) -> str:
    label = f"'{reminder.name}'" if reminder.name else f"'{reminder.instruction}'"
    return (
        f"{reminder.id}: {label} — {_render_schedule(reminder.schedule)}, "
        f"next {reminder.next_run_at:%Y-%m-%d %H:%M %Z}"
    )


def _render_schedule(schedule: ReminderSchedule) -> str:
    match schedule:
        case RemindOnce(when=when):
            return f"once at {when:%Y-%m-%d %H:%M %Z}"
        case RemindEvery(seconds=seconds):
            return f"every {seconds / 60:g} min"
        case RemindOnCron(expression=expression, timezone=timezone):
            return f"cron '{expression}' ({timezone})"
