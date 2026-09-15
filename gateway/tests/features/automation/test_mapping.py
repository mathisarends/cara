from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from gateway.features.automation.domain import (
    AtSchedule,
    Automation,
    AutomationSchedule,
    CronSchedule,
    IntervalSchedule,
    PromptAction,
    SessionTarget,
)
from gateway.features.automation.presentation.rpc.mapping import (
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
    automation_id = uuid4()
    session_id = uuid4()
    automation = Automation(
        id=automation_id,
        created_at=created_at,
        owner_id="owner",
        target=SessionTarget(session_id),
        schedule=IntervalSchedule(every=timedelta(minutes=30)),
        action=PromptAction("Drink water"),
        name="Hydration",
        next_run_at=next_run_at,
    )

    response = automation_response(automation)

    assert response.id == automation_id
    assert response.owner_id == "owner"
    assert response.name == "Hydration"
    assert response.created_at == created_at
    assert response.next_run_at == next_run_at
    assert response.schedule == WireIntervalSchedule(
        every_seconds=1800,
        run_immediately=False,
    )
    assert response.target == SessionAutomationTarget(session_id=session_id)
    assert response.payload == ReminderAutomationPayload(instruction="Drink water")


def test_automation_requires_an_owner() -> None:
    with pytest.raises(ValueError, match="owner id"):
        Automation(
            id=uuid4(),
            created_at=datetime.now(UTC),
            owner_id=" ",
            target=SessionTarget(uuid4()),
            schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
            action=PromptAction("Drink water"),
            next_run_at=datetime(2027, 1, 1, tzinfo=UTC),
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
    wire_target = SessionAutomationTarget(session_id=session_id)

    assert target_response(domain_target) == wire_target
    assert automation_target(wire_target) == domain_target


def test_prompt_action_is_read_from_the_reminder_payload() -> None:
    payload = ReminderAutomationPayload(instruction="Drink water")

    assert prompt_action(payload) == PromptAction("Drink water")
