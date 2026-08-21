from datetime import UTC, datetime, timedelta
from uuid import uuid4

from gateway.features.automation.application import AutomationService
from gateway.features.automation.domain import (
    AutomationEnvelope,
    ReminderPayload,
    SessionAutomationTarget,
)
from gateway.features.automation.presentation.rpc_methods import AutomationRpcMethods
from gateway.features.automation.presentation.schemas import (
    GetAutomationParams,
    ListAutomationsParams,
)
from scheduler import MemoryJobStore, ScheduledRun, Scheduler


async def _runner(run: ScheduledRun[AutomationEnvelope]) -> None:
    pass


async def test_rpc_lists_and_gets_typed_automations() -> None:
    scheduler = Scheduler(_runner, MemoryJobStore[AutomationEnvelope]())
    methods = AutomationRpcMethods(AutomationService(scheduler))
    session_id = uuid4()
    await scheduler.interval(
        every=timedelta(minutes=30),
        run_immediately=False,
        payload=AutomationEnvelope(
            schema_version=1,
            target=SessionAutomationTarget(kind="session", session_id=session_id),
            payload=ReminderPayload(
                kind="reminder",
                message="Drink water",
                created_from_turn_id=uuid4(),
            ),
        ),
        job_id="drink-water",
        name="Hydration",
    )

    listed = await methods.list_automations(
        ListAutomationsParams(session_id=session_id)
    )
    fetched = await methods.get_automation(
        GetAutomationParams(
            session_id=session_id,
            automation_id="drink-water",
        )
    )

    assert listed.automations == (fetched,)
    assert fetched.name == "Hydration"
    assert fetched.schedule.kind == "interval"
    assert fetched.target.session_id == session_id
    assert fetched.payload.kind == "reminder"
    assert fetched.created_at <= datetime.now(UTC)
