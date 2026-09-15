import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from agenttoolkit import ToolContext

from agent.clock import LocalClock
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
_CLOCK = LocalClock(
    "Europe/Berlin",
    clock=lambda: datetime(2026, 8, 25, 12, tzinfo=UTC),
)
_NEW_ID = uuid4()


class _StubReminders(Reminders):
    def __init__(self, scheduled: tuple[Reminder, ...] = ()) -> None:
        self.created: list[tuple[str, ReminderSchedule, str | None]] = []
        self.updated: list[tuple[UUID, str, ReminderSchedule]] = []
        self.deleted: list[UUID] = []
        self._scheduled = scheduled

    async def list(self) -> tuple[Reminder, ...]:
        return self._scheduled

    async def create(
        self,
        *,
        instruction: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder:
        self.created.append((instruction, schedule, name))
        return _reminder(_NEW_ID, instruction, schedule, name)

    async def update(
        self,
        reminder_id: UUID,
        *,
        instruction: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder:
        self.updated.append((reminder_id, instruction, schedule))
        return _reminder(reminder_id, instruction, schedule, name)

    async def delete(self, reminder_id: UUID) -> None:
        self.deleted.append(reminder_id)


def _reminder(
    reminder_id: UUID,
    instruction: str,
    schedule: ReminderSchedule,
    name: str | None = None,
) -> Reminder:
    return Reminder(
        id=reminder_id,
        instruction=instruction,
        schedule=schedule,
        next_run_at=datetime(2026, 8, 26, 5, 30, tzinfo=UTC),
        name=name,
    )


def _context(reminders: Reminders | None, tmp_path: Path) -> ToolContext:
    from agenttoolkit.builtins import LocalWorkspace

    return _create_tool_context(
        reminders,
        workspace=LocalWorkspace(tmp_path),
        clock=_CLOCK,
    )


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


def test_create_reminder_schema_is_one_time_only(tmp_path: Path) -> None:
    tools = _create_tools(_context(_StubReminders(), tmp_path))
    schema = next(
        item
        for item in tools.get_schema("openai")
        if item["function"]["name"] == "create_reminder"
    )

    function = schema["function"]
    properties = function["parameters"]["properties"]
    assert "run_at" in function["parameters"]["required"]
    assert "message" not in properties
    assert "schedule" not in properties
    assert "every_minutes" not in properties
    assert "cron" not in properties


def test_create_reminder_localises_a_naive_run_at(tmp_path: Path) -> None:
    stub = _StubReminders()

    result = _run(
        stub,
        tmp_path,
        "create_reminder",
        {
            "run_at": "2026-08-26T07:30:00",
            "instruction": "Zahnarzt",
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
    assert result.startswith(
        f"Scheduled: {_NEW_ID}: 'Zahnarzt' — once at 2026-08-26 07:30"
    )


def test_create_reminder_rejects_a_past_local_time(tmp_path: Path) -> None:
    result = _run(
        _StubReminders(),
        tmp_path,
        "create_reminder",
        {
            "run_at": "2000-01-01T12:00:00",
            "timezone": "Europe/Berlin",
            "instruction": "Wake the user",
        },
    )

    assert isinstance(result, ToolFailure)
    assert "must be in the future" in result
    assert "Current local time in Europe/Berlin" in result


def test_create_reminder_reports_an_unknown_timezone(tmp_path: Path) -> None:
    result = _run(
        _StubReminders(),
        tmp_path,
        "create_reminder",
        {
            "run_at": "2026-08-26T07:30:00",
            "timezone": "Mars/Olympus_Mons",
            "instruction": "Standup",
        },
    )

    assert isinstance(result, ToolFailure)
    assert "Unknown timezone" in result


def test_list_reminders_renders_every_schedule_kind(tmp_path: Path) -> None:
    once, every, cron = uuid4(), uuid4(), uuid4()
    scheduled = (
        _reminder(
            once, "Zahnarzt", RemindOnce(when=datetime(2026, 8, 26, 7, 30, tzinfo=UTC))
        ),
        _reminder(every, "Wasser", RemindEvery(seconds=5400.0)),
        _reminder(
            cron, "Standup", RemindOnCron("0 9 * * 1-5", "Europe/Berlin"), "Standup"
        ),
    )

    result = _run(_StubReminders(scheduled), tmp_path, "list_reminders", {})

    assert f"{once}: 'Zahnarzt' — once at 2026-08-26 07:30" in result
    assert f"{every}: 'Wasser' — every 90 min" in result
    assert f"{cron}: 'Standup' — cron '0 9 * * 1-5' (Europe/Berlin)" in result


def test_list_reminders_reports_an_empty_schedule(tmp_path: Path) -> None:
    assert _run(_StubReminders(), tmp_path, "list_reminders", {}) == (
        "No reminders are scheduled."
    )


def test_update_and_delete_reach_the_gateway_port(tmp_path: Path) -> None:
    stub = _StubReminders()
    reminder_id = uuid4()

    _run(
        stub,
        tmp_path,
        "update_reminder",
        {
            "reminder_id": str(reminder_id),
            "run_at": "2026-08-26T07:30:00",
            "instruction": "Standup",
        },
    )
    deleted = _run(stub, tmp_path, "delete_reminder", {"reminder_id": str(reminder_id)})

    assert stub.updated == [
        (
            reminder_id,
            "Standup",
            RemindOnce(when=datetime(2026, 8, 26, 7, 30, tzinfo=_BERLIN)),
        )
    ]
    assert stub.deleted == [reminder_id]
    assert deleted == f"Deleted reminder {reminder_id}."


@pytest.mark.parametrize("tool", ["update_reminder", "delete_reminder"])
def test_reminder_tools_require_a_valid_id(tmp_path: Path, tool: str) -> None:
    result = _run(_StubReminders(), tmp_path, tool, {"reminder_id": "not-a-uuid"})

    assert isinstance(result, ToolFailure)
