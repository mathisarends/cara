import asyncio
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from agenttoolkit import ToolContext

from agent.tools.factory import _create_tool_context, _create_tools
from agent.tools.handler import (
    Reminder,
    Reminders,
    ReminderSchedule,
    RemindEvery,
    RemindOnce,
    RemindOnCron,
)
from agent.tools.middleware import ToolFailure

_BERLIN = ZoneInfo("Europe/Berlin")


class _StubReminders(Reminders):
    def __init__(self, scheduled: tuple[Reminder, ...] = ()) -> None:
        self.created: list[tuple[str, ReminderSchedule, str | None]] = []
        self.updated: list[tuple[str, str, ReminderSchedule]] = []
        self.deleted: list[str] = []
        self._scheduled = scheduled

    async def list(self) -> tuple[Reminder, ...]:
        return self._scheduled

    async def create(
        self,
        *,
        message: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder:
        self.created.append((message, schedule, name))
        return _reminder("new", message, schedule, name)

    async def update(
        self,
        reminder_id: str,
        *,
        message: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder:
        self.updated.append((reminder_id, message, schedule))
        return _reminder(reminder_id, message, schedule, name)

    async def delete(self, reminder_id: str) -> None:
        self.deleted.append(reminder_id)


def _reminder(
    reminder_id: str,
    message: str,
    schedule: ReminderSchedule,
    name: str | None = None,
) -> Reminder:
    return Reminder(
        id=reminder_id,
        message=message,
        schedule=schedule,
        next_run_at=datetime(2026, 8, 26, 5, 30, tzinfo=UTC),
        name=name,
    )


def _context(reminders: Reminders | None, tmp_path: Path) -> ToolContext:
    from agenttoolkit.builtins import LocalWorkspace

    return _create_tool_context(reminders, workspace=LocalWorkspace(tmp_path))


def _run(reminders: Reminders | None, tmp_path: Path, name: str, arguments: dict):
    tools = _create_tools(_context(reminders, tmp_path))
    return asyncio.run(tools.execute(name, arguments))


def test_reminder_tools_are_hidden_without_a_gateway_connection(tmp_path: Path) -> None:
    tools = _create_tools(_context(None, tmp_path))

    names = {schema.name for schema in tools.get_schema()}

    assert not names & {
        "list_reminders",
        "create_reminder",
        "update_reminder",
        "delete_reminder",
    }


def test_reminder_tools_appear_once_reminders_are_provided(tmp_path: Path) -> None:
    tools = _create_tools(_context(_StubReminders(), tmp_path))

    names = {schema.name for schema in tools.get_schema()}

    assert {"list_reminders", "create_reminder", "delete_reminder"} <= names


def test_create_reminder_localises_a_naive_run_at(tmp_path: Path) -> None:
    stub = _StubReminders()

    result = _run(
        stub,
        tmp_path,
        "create_reminder",
        {
            "schedule": "once",
            "run_at": "2026-08-26T07:30:00",
            "message": "Zahnarzt",
            "name": "Zahnarzt",
        },
    )

    assert stub.created == [
        (
            "Zahnarzt",
            RemindOnce(when=datetime(2026, 8, 26, 7, 30, tzinfo=_BERLIN)),
            "Zahnarzt",
        )
    ]
    assert result.startswith("Scheduled: new: 'Zahnarzt' — once at 2026-08-26 07:30")


def test_create_reminder_converts_minutes_to_seconds(tmp_path: Path) -> None:
    stub = _StubReminders()

    _run(
        stub,
        tmp_path,
        "create_reminder",
        {"schedule": "every", "every_minutes": 90, "message": "Wasser trinken"},
    )

    assert stub.created == [("Wasser trinken", RemindEvery(seconds=5400.0), None)]


def test_create_reminder_reports_a_missing_schedule_field(tmp_path: Path) -> None:
    result = _run(
        _StubReminders(),
        tmp_path,
        "create_reminder",
        {"schedule": "cron", "message": "Standup"},
    )

    assert isinstance(result, ToolFailure)
    assert "params.cron is required" in result


def test_create_reminder_reports_an_unknown_timezone(tmp_path: Path) -> None:
    result = _run(
        _StubReminders(),
        tmp_path,
        "create_reminder",
        {
            "schedule": "cron",
            "cron": "0 9 * * *",
            "timezone": "Mars/Olympus_Mons",
            "message": "Standup",
        },
    )

    assert isinstance(result, ToolFailure)
    assert "Unknown timezone" in result


def test_list_reminders_renders_every_schedule_kind(tmp_path: Path) -> None:
    scheduled = (
        _reminder(
            "a", "Zahnarzt", RemindOnce(when=datetime(2026, 8, 26, 7, 30, tzinfo=UTC))
        ),
        _reminder("b", "Wasser", RemindEvery(seconds=5400.0)),
        _reminder(
            "c", "Standup", RemindOnCron("0 9 * * 1-5", "Europe/Berlin"), "Standup"
        ),
    )

    result = _run(_StubReminders(scheduled), tmp_path, "list_reminders", {})

    assert "a: 'Zahnarzt' — once at 2026-08-26 07:30" in result
    assert "b: 'Wasser' — every 90 min" in result
    assert "c: 'Standup' — cron '0 9 * * 1-5' (Europe/Berlin)" in result


def test_list_reminders_reports_an_empty_schedule(tmp_path: Path) -> None:
    assert _run(_StubReminders(), tmp_path, "list_reminders", {}) == (
        "No reminders are scheduled."
    )


def test_update_and_delete_reach_the_gateway_port(tmp_path: Path) -> None:
    stub = _StubReminders()

    _run(
        stub,
        tmp_path,
        "update_reminder",
        {
            "reminder_id": "a",
            "schedule": "cron",
            "cron": "0 9 * * 1-5",
            "message": "Standup",
        },
    )
    deleted = _run(stub, tmp_path, "delete_reminder", {"reminder_id": "a"})

    assert stub.updated == [
        ("a", "Standup", RemindOnCron("0 9 * * 1-5", "Europe/Berlin"))
    ]
    assert stub.deleted == ["a"]
    assert deleted == "Deleted reminder a."


@pytest.mark.parametrize("tool", ["update_reminder", "delete_reminder"])
def test_reminder_tools_require_an_id(tmp_path: Path, tool: str) -> None:
    result = _run(_StubReminders(), tmp_path, tool, {"reminder_id": ""})

    assert isinstance(result, ToolFailure)
