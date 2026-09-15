from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from gateway.features.automation.domain import (
    AtSchedule,
    Automation,
    AutomationSchedule,
    ChannelTarget,
    CronSchedule,
    IntervalSchedule,
    PromptAction,
    SessionTarget,
)
from gateway.features.automation.infrastructure.repository import (
    SQLAutomationRepository,
)

_HOURLY = IntervalSchedule(every=timedelta(hours=1))


@pytest.mark.parametrize(
    "schedule",
    [
        AtSchedule(run_at=datetime(2027, 1, 1, 9, tzinfo=UTC)),
        IntervalSchedule(every=timedelta(minutes=90), run_immediately=True),
        CronSchedule(expression="0 9 * * 1-5", timezone="Europe/Berlin"),
    ],
)
async def test_save_round_trips_every_schedule_kind(
    automation_repository: SQLAutomationRepository,
    schedule: AutomationSchedule,
) -> None:
    automation = _automation("owner", schedule=schedule, name="Stretch")

    await automation_repository.save(automation)
    stored = await automation_repository.find_by_id(automation.id)

    assert stored is not None
    assert _state(stored) == _state(automation)


async def test_find_by_owner_returns_only_that_owners_automations(
    automation_repository: SQLAutomationRepository,
) -> None:
    mine = await automation_repository.save(_automation("owner"))
    await automation_repository.save(_automation("someone-else"))

    found = await automation_repository.find_by_owner("owner")

    assert [automation.id for automation in found] == [mine.id]


async def test_save_round_trips_a_channel_target(
    automation_repository: SQLAutomationRepository,
) -> None:
    automation = Automation.create(
        owner_id="owner",
        target=ChannelTarget("voice"),
        schedule=_HOURLY,
        action=PromptAction("Stretch"),
        next_run_at=datetime(2027, 1, 1, 9, tzinfo=UTC),
    )

    await automation_repository.save(automation)

    stored = await automation_repository.find_by_id(automation.id)
    assert stored is not None
    assert stored.target == ChannelTarget("voice")


async def test_remove_deletes_the_automation(
    automation_repository: SQLAutomationRepository,
) -> None:
    automation = await automation_repository.save(_automation("owner"))

    await automation_repository.remove(automation)

    assert await automation_repository.find_all() == ()


def _automation(
    owner_id: str,
    *,
    schedule: AutomationSchedule = _HOURLY,
    name: str | None = None,
) -> Automation:
    return Automation.create(
        owner_id=owner_id,
        target=SessionTarget(uuid4()),
        schedule=schedule,
        action=PromptAction("Stretch"),
        next_run_at=datetime(2027, 1, 1, 9, tzinfo=UTC),
        name=name,
    )


def _state(automation: Automation) -> tuple[object, ...]:
    return (
        automation.id,
        automation.created_at,
        automation.owner_id,
        automation.target,
        automation.schedule,
        automation.action,
        automation.next_run_at,
        automation.name,
    )
