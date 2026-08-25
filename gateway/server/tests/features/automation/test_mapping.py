from datetime import UTC, datetime
from uuid import uuid4

import pytest

from gateway.features.automation.domain import (
    AutomationEnvelope,
    ReminderPayload,
    SessionAutomationTarget,
)
from gateway.features.automation.presentation.mapping import automation_response
from scheduler import At, Cron, ScheduledJob, Trigger


@pytest.mark.parametrize(
    ("trigger", "expected"),
    [
        (At(datetime(2027, 1, 1, tzinfo=UTC)), {"kind": "at"}),
        (
            Cron("0 8 * * *", UTC),
            {"kind": "cron", "expression": "0 8 * * *", "timezone": "UTC"},
        ),
    ],
)
def test_automation_response_maps_schedule_types(
    trigger: Trigger,
    expected: dict[str, str],
) -> None:
    now = datetime.now(UTC)
    response = automation_response(
        ScheduledJob(
            id="job",
            trigger=trigger,
            payload=AutomationEnvelope(
                schema_version=2,
                target=SessionAutomationTarget(
                    kind="session",
                    session_id=uuid4(),
                ),
                payload=ReminderPayload(
                    kind="reminder",
                    instruction="Test",
                    created_from_turn_id=uuid4(),
                ),
            ),
            created_at=now,
            next_run_at=now,
        )
    )

    schedule = response.schedule.model_dump(mode="json")
    assert schedule.items() >= expected.items()
