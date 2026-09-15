from datetime import UTC, datetime
from uuid import uuid4

import httpx2
import pytest
from pydantic import SecretStr

from agent.tools.handler import GatewayConnection, GatewayReminders
from agent.tools.handler.gateway_reminders import _automation_schedule, _reminder
from agent.tools.handler.ports import RemindEvery, RemindOnce, RemindOnCron
from agent.tools.middleware import ToolError
from gateway_rest_client import (
    AtSchedule,
    AutomationResponse,
    AutomationScheduleKind,
    AutomationTarget,
    CronSchedule,
    IntervalSchedule,
    ReminderPayload,
)

_SESSION_ID = uuid4()
_AUTOMATION_ID = uuid4()
_HOURLY = IntervalSchedule(
    kind=AutomationScheduleKind.INTERVAL, every_seconds=5400, run_immediately=False
)


def _automation(schedule) -> AutomationResponse:
    return AutomationResponse(
        id=_AUTOMATION_ID,
        owner_id="local",
        name="Zahnarzt",
        created_at=datetime(2026, 8, 25, tzinfo=UTC),
        next_run_at=datetime(2026, 8, 26, 5, 30, tzinfo=UTC),
        schedule=schedule,
        target=AutomationTarget(session_id=_SESSION_ID),
        payload=ReminderPayload(instruction="Zahnarzt"),
    )


def _serve(
    monkeypatch: pytest.MonkeyPatch,
    handler,
) -> None:
    client_type = httpx2.AsyncClient
    monkeypatch.setattr(
        httpx2,
        "AsyncClient",
        lambda: client_type(transport=httpx2.MockTransport(handler)),
    )


def test_gateway_reminders_require_a_token() -> None:
    with pytest.raises(ValueError, match="gateway token"):
        GatewayReminders(GatewayConnection(token=None), session_id=_SESSION_ID)


def test_gateway_connection_reads_the_cli_token_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CARA_GATEWAY_TOKEN", "secret")

    connection = GatewayConnection()

    assert connection.token == SecretStr("secret")
    assert connection.url == "http://127.0.0.1:8000"
    assert connection.owner_id == "local"


def test_gateway_connection_reads_the_owner_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CARA_GATEWAY_OWNER_ID", "mathis")

    assert GatewayConnection().owner_id == "mathis"


async def test_list_reads_the_owner_automations_with_the_gateway_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        body = {"automations": [_automation(_HOURLY).model_dump(mode="json")]}
        return httpx2.Response(200, json=body)

    _serve(monkeypatch, handler)
    reminders = GatewayReminders(
        GatewayConnection(url="http://gateway.test", token=SecretStr("secret")),
        session_id=_SESSION_ID,
    )

    listed = await reminders.list()

    assert [reminder.id for reminder in listed] == [_AUTOMATION_ID]
    assert requests[0].url == "http://gateway.test/v1/owners/local/automations"
    assert requests[0].headers["Authorization"] == "Bearer secret"


async def test_gateway_rejections_become_tool_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, lambda request: httpx2.Response(401, json={}))
    reminders = GatewayReminders(
        GatewayConnection(token=SecretStr("wrong")),
        session_id=_SESSION_ID,
    )

    with pytest.raises(ToolError, match="rejected"):
        await reminders.delete(_AUTOMATION_ID)


def test_reminder_maps_every_schedule_kind_from_the_gateway() -> None:
    run_at = datetime(2026, 8, 26, 7, 30, tzinfo=UTC)

    assert _reminder(
        _automation(AtSchedule(kind=AutomationScheduleKind.AT, run_at=run_at))
    ).schedule == RemindOnce(when=run_at)
    assert _reminder(_automation(_HOURLY)).schedule == RemindEvery(seconds=5400)
    assert _reminder(
        _automation(
            CronSchedule(
                kind=AutomationScheduleKind.CRON,
                expression="0 9 * * *",
                timezone="Europe/Berlin",
            )
        )
    ).schedule == RemindOnCron(expression="0 9 * * *", timezone="Europe/Berlin")


def test_reminder_carries_the_instruction_and_next_run() -> None:
    reminder = _reminder(_automation(_HOURLY))

    assert reminder.id == _AUTOMATION_ID
    assert reminder.name == "Zahnarzt"
    assert reminder.instruction == "Zahnarzt"
    assert reminder.next_run_at == datetime(2026, 8, 26, 5, 30, tzinfo=UTC)


def test_intervals_never_fire_immediately_when_scheduled() -> None:
    assert _automation_schedule(RemindEvery(seconds=5400)) == _HOURLY


def test_schedules_round_trip_through_the_gateway_contract() -> None:
    for schedule in (
        RemindOnce(when=datetime(2026, 8, 26, 7, 30, tzinfo=UTC)),
        RemindEvery(seconds=5400),
        RemindOnCron(expression="0 9 * * 1-5", timezone="Europe/Berlin"),
    ):
        assert (
            _reminder(_automation(_automation_schedule(schedule))).schedule == schedule
        )
