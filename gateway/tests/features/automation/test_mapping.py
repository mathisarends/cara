from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from gateway.features.automation.domain import (
    AtSchedule,
    Automation,
    AutomationOrigin,
    AutomationSchedule,
    CronSchedule,
    IntervalSchedule,
    PromptAction,
    SessionTarget,
)
from gateway.features.automation.presentation.rpc.mapping import (
    automation_origin,
    automation_response,
    automation_schedule,
    automation_target,
    prompt_action,
    schedule_response,
    target_response,
)
from gateway.features.automation.presentation.rpc.models import (
    AtSchedule as WireAtSchedule,
)
from gateway.features.automation.presentation.rpc.models import (
    CronSchedule as WireCronSchedule,
)
from gateway.features.automation.presentation.rpc.models import (
    IntervalSchedule as WireIntervalSchedule,
)
from gateway.features.automation.presentation.rpc.models import (
    ReminderAutomationPayload,
    SessionAutomationTarget,
)


def test_automation_response_maps_a_domain_automation_to_the_wire_shape() -> None:
    created_at = datetime(2027, 1, 1, tzinfo=UTC)
    next_run_at = datetime(2027, 1, 2, tzinfo=UTC)
    session_id = uuid4()
    turn_id = uuid4()
    automation = Automation(
        id="reminder-1",
        created_at=created_at,
        owner_id="owner",
        target=SessionTarget(session_id),
        schedule=IntervalSchedule(every=timedelta(minutes=30)),
        action=PromptAction("Drink water"),
        origin=AutomationOrigin(turn_id),
        name="Hydration",
        next_run_at=next_run_at,
    )

    response = automation_response(automation)

    assert response.id == "reminder-1"
    assert response.owner_id == "owner"
    assert response.name == "Hydration"
    assert response.created_at == created_at
    assert response.next_run_at == next_run_at
    assert response.schedule == WireIntervalSchedule(
        every_seconds=1800,
        run_immediately=False,
    )
    assert response.target == SessionAutomationTarget(
        kind="session",
        session_id=session_id,
    )
    assert response.payload == ReminderAutomationPayload(
        kind="reminder",
        instruction="Drink water",
        created_from_turn_id=turn_id,
    )


def test_automation_response_requires_a_scheduled_next_run() -> None:
    automation = Automation(
        id="reminder-1",
        created_at=datetime.now(UTC),
        owner_id="owner",
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Drink water"),
        origin=AutomationOrigin(uuid4()),
    )

    with pytest.raises(ValueError, match="has not been scheduled"):
        automation_response(automation)


def test_automation_requires_an_owner() -> None:
    with pytest.raises(ValueError, match="owner id"):
        Automation(
            id="reminder-1",
            created_at=datetime.now(UTC),
            owner_id=" ",
            target=SessionTarget(uuid4()),
            schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
            action=PromptAction("Drink water"),
            origin=AutomationOrigin(uuid4()),
        )


@pytest.mark.parametrize(
    ("domain_schedule", "wire_schedule"),
    [
        (
            AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
            WireAtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        ),
        (
            IntervalSchedule(every=timedelta(minutes=30), run_immediately=True),
            WireIntervalSchedule(every_seconds=1800, run_immediately=True),
        ),
        (
            CronSchedule(expression="0 8 * * *", timezone="UTC"),
            WireCronSchedule(expression="0 8 * * *", timezone="UTC"),
        ),
    ],
)
def test_schedule_mapping_round_trips_between_domain_and_wire(
    domain_schedule: AutomationSchedule,
    wire_schedule: WireAtSchedule | WireIntervalSchedule | WireCronSchedule,
) -> None:
    assert schedule_response(domain_schedule) == wire_schedule
    assert automation_schedule(wire_schedule) == domain_schedule


def test_target_mapping_round_trips_between_domain_and_wire() -> None:
    session_id = uuid4()
    domain_target = SessionTarget(session_id)
    wire_target = SessionAutomationTarget(kind="session", session_id=session_id)

    assert target_response(domain_target) == wire_target
    assert automation_target(wire_target) == domain_target


def test_prompt_action_and_origin_are_read_from_the_reminder_payload() -> None:
    turn_id = uuid4()
    payload = ReminderAutomationPayload(
        kind="reminder",
        instruction="Drink water",
        created_from_turn_id=turn_id,
    )

    assert prompt_action(payload) == PromptAction("Drink water")
    assert automation_origin(payload) == AutomationOrigin(turn_id)
