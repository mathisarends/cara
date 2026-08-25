from datetime import UTC, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from agenttoolkit import Inject, Tools, provided
from pydantic import Field

from agent.tools.handler import (
    Reminder,
    Reminders,
    ReminderSchedule,
    RemindEvery,
    RemindOnce,
    RemindOnCron,
)
from agent.tools.middleware import ToolError
from agent.tools.params import ToolParams

_DEFAULT_TIMEZONE = "Europe/Berlin"


class ReminderScheduleKind(StrEnum):
    ONCE = "once"
    EVERY = "every"
    CRON = "cron"


class _ScheduleParams(ToolParams):
    schedule: ReminderScheduleKind = Field(
        description=(
            "When the reminder fires: 'once' at params.run_at, 'every' "
            "params.every_minutes repeatedly, or 'cron' on params.cron."
        )
    )
    run_at: datetime | None = Field(
        default=None,
        description=(
            "Local wall-clock time for a 'once' reminder, e.g. "
            "'2026-08-26T07:30:00'. Required when params.schedule is 'once'."
        ),
    )
    every_minutes: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Minutes between runs of an 'every' reminder. Required when "
            "params.schedule is 'every'."
        ),
    )
    cron: str | None = Field(
        default=None,
        description=(
            "Five-field cron expression, e.g. '0 9 * * 1-5'. Required when "
            "params.schedule is 'cron'."
        ),
    )
    timezone: str = Field(
        default=_DEFAULT_TIMEZONE,
        description=(
            "IANA timezone the times are meant in, e.g. 'Europe/Berlin'. "
            "Only change this when the user is explicitly in another zone."
        ),
    )
    instruction: str = Field(
        description=(
            "Complete, self-contained instruction for the future agent run, in the "
            "user's own intent and language. Name every action, its order, target, and "
            "relevant tool capability (e.g. play bird sounds on Sonos). Do not invent "
            "or test exact CLI syntax now; the future run resolves it from its tools "
            "and skills. If no tool is needed, store the response to give."
        )
    )
    name: str | None = Field(
        default=None,
        description="Short label for the reminder, e.g. 'Morning stand-up'.",
    )


class CreateReminderParams(_ScheduleParams):
    pass


class UpdateReminderParams(_ScheduleParams):
    reminder_id: str = Field(
        min_length=1,
        description="Id of the reminder to replace, as returned by list_reminders.",
    )


class DeleteReminderParams(ToolParams):
    reminder_id: str = Field(
        min_length=1,
        description="Id of the reminder to delete, as returned by list_reminders.",
    )


class ListRemindersParams(ToolParams):
    pass


def register_reminder_tools(tools: Tools) -> None:
    available = provided(Reminders)

    @tools.tool(
        description=(
            "List the reminders scheduled for this conversation, with their "
            "ids and next run times."
        ),
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
        description=(
            "Schedule a future agent run for this conversation, once at a given "
            "time, repeatedly every few minutes, or on a cron expression. The future "
            "run can speak to the user and call tools. Store the complete executable "
            "instruction, including requested actions and tool use, rather than only "
            "a reminder topic. Do not execute, test, or rehearse the future task in "
            "the current turn, and do not call other tools merely to discover command "
            "syntax. Create exactly one reminder unless the user explicitly requests "
            "multiple schedules."
        ),
        params=CreateReminderParams,
        available_when=available,
    )
    async def create_reminder(
        params: CreateReminderParams,
        reminders: Inject[Reminders],
    ) -> str:
        reminder = await reminders.create(
            instruction=params.instruction,
            schedule=_schedule(params),
            name=params.name,
        )
        return (
            f"Scheduled: {_render_reminder(reminder)}\n"
            "Scheduling is complete. Do not execute or test the future task now. "
            "Do not list, update, delete, or create another reminder for this request. "
            "Stop using tools and confirm the scheduled time to the user."
        )

    @tools.tool(
        description=(
            "Replace an existing scheduled agent run. Instruction and schedule are "
            "both overwritten, so pass the complete executable instruction and full "
            "schedule, not only what changed."
        ),
        params=UpdateReminderParams,
        available_when=available,
    )
    async def update_reminder(
        params: UpdateReminderParams,
        reminders: Inject[Reminders],
    ) -> str:
        reminder = await reminders.update(
            params.reminder_id,
            instruction=params.instruction,
            schedule=_schedule(params),
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


def _schedule(params: _ScheduleParams) -> ReminderSchedule:
    timezone = _timezone(params.timezone)
    match params.schedule:
        case ReminderScheduleKind.ONCE:
            if params.run_at is None:
                raise ToolError("params.run_at is required for a 'once' reminder")
            when = _localised(params.run_at, timezone)
            if when.astimezone(UTC) <= datetime.now(UTC):
                now = datetime.now(timezone)
                current_time = now.isoformat(timespec="seconds")
                raise ToolError(
                    "params.run_at must be in the future. "
                    f"Current local time in {timezone.key} is {current_time}"
                )
            return RemindOnce(when=when)
        case ReminderScheduleKind.EVERY:
            if params.every_minutes is None:
                raise ToolError(
                    "params.every_minutes is required for an 'every' reminder"
                )
            return RemindEvery(seconds=params.every_minutes * 60)
        case ReminderScheduleKind.CRON:
            if params.cron is None:
                raise ToolError("params.cron is required for a 'cron' reminder")
            return RemindOnCron(expression=params.cron, timezone=params.timezone)


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
