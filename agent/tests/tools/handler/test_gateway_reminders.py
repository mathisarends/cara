from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import SecretStr

from agent.tools.handler import GatewayConnection, GatewayReminders
from agent.tools.handler.gateway_reminders import _automation_schedule, _reminder
from agent.tools.handler.ports import RemindEvery, RemindOnce, RemindOnCron
from gateway_client.models import (
    AtSchedule,
    AutomationResponse,
    AutomationTarget,
    CronSchedule,
    IntervalSchedule,
    ReminderAutomationPayload,
)

_SESSION_ID = uuid4()
_TURN_ID = uuid4()


def _automation(schedule) -> AutomationResponse:
    return AutomationResponse(
        id="a",
        owner_id="local",
        name="Zahnarzt",
        created_at=datetime(2026, 8, 25, tzinfo=UTC),
        next_run_at=datetime(2026, 8, 26, 5, 30, tzinfo=UTC),
        schedule=schedule,
        target=AutomationTarget(kind="session", session_id=_SESSION_ID),
        payload=ReminderAutomationPayload(
            kind="reminder",
            instruction="Zahnarzt",
            created_from_turn_id=_TURN_ID,
        ),
    )


def test_gateway_reminders_require_a_token() -> None:
    with pytest.raises(ValueError, match="gateway token"):
        GatewayReminders(
            GatewayConnection(token=None),
            session_id=_SESSION_ID,
            turn_id=_TURN_ID,
        )


def test_gateway_connection_reads_the_cli_token_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CARA_GATEWAY_TOKEN", "secret")

    connection = GatewayConnection()

    assert connection.token == SecretStr("secret")
    assert connection.url == "ws://127.0.0.1:8000/v1/gateway"
    assert connection.owner_id == "local"


def test_gateway_connection_reads_the_owner_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CARA_GATEWAY_OWNER_ID", "mathis")

    assert GatewayConnection().owner_id == "mathis"


def test_reminder_maps_every_schedule_kind_from_the_gateway() -> None:
    run_at = datetime(2026, 8, 26, 7, 30, tzinfo=UTC)

    assert _reminder(_automation(AtSchedule(run_at=run_at))).schedule == RemindOnce(
        when=run_at
    )
    assert _reminder(
        _automation(IntervalSchedule(every_seconds=5400, run_immediately=False))
    ).schedule == RemindEvery(seconds=5400)
    assert _reminder(
        _automation(CronSchedule(expression="0 9 * * *", timezone="Europe/Berlin"))
    ).schedule == RemindOnCron(expression="0 9 * * *", timezone="Europe/Berlin")


def test_reminder_carries_the_instruction_and_next_run() -> None:
    reminder = _reminder(
        _automation(IntervalSchedule(every_seconds=60, run_immediately=False))
    )

    assert reminder.id == "a"
    assert reminder.name == "Zahnarzt"
    assert reminder.instruction == "Zahnarzt"
    assert reminder.next_run_at == datetime(2026, 8, 26, 5, 30, tzinfo=UTC)


def test_intervals_never_fire_immediately_when_scheduled() -> None:
    schedule = _automation_schedule(RemindEvery(seconds=5400))

    assert schedule == IntervalSchedule(every_seconds=5400, run_immediately=False)


def test_schedules_round_trip_through_the_gateway_contract() -> None:
    for schedule in (
        RemindOnce(when=datetime(2026, 8, 26, 7, 30, tzinfo=UTC)),
        RemindEvery(seconds=5400),
        RemindOnCron(expression="0 9 * * 1-5", timezone="Europe/Berlin"),
    ):
        assert (
            _reminder(_automation(_automation_schedule(schedule))).schedule == schedule
        )
