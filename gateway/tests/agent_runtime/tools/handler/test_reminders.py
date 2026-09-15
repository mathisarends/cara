from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from gateway.agent_runtime.tools.handler import GatewayReminders, RemindOnce
from gateway.features.automation.application import AutomationService
from gateway.features.automation.domain import (
    AtSchedule,
    Automation,
    ChannelTarget,
    PromptAction,
    SessionTarget,
)
from gateway.shared import UnitOfWork

_OWNER_ID = "owner"
_SESSION_ID = uuid4()
_RUN_AT = datetime(2026, 9, 16, 8, tzinfo=UTC)


class _AutomationService:
    def __init__(self) -> None:
        self.created: tuple[object, ...] | None = None

    async def list(self, owner_id: str) -> tuple[Automation, ...]:
        assert owner_id == _OWNER_ID
        return ()

    async def create(self, owner_id: str, **values: object) -> Automation:
        self.created = (owner_id, values)
        return Automation.create(
            owner_id=owner_id,
            target=cast(SessionTarget, values["target"]),
            schedule=cast(AtSchedule, values["schedule"]),
            action=cast(PromptAction, values["action"]),
            next_run_at=_RUN_AT,
            name=cast(str | None, values["name"]),
        )


class _UnitOfWork(UnitOfWork[AutomationService]):
    def __init__(self, service: _AutomationService) -> None:
        self._service = service

    @asynccontextmanager
    async def __call__(self):
        yield cast(AutomationService, self._service)


async def test_reminders_call_the_gateway_service_in_process() -> None:
    service = _AutomationService()
    reminders = GatewayReminders(
        _UnitOfWork(service),
        owner_id=_OWNER_ID,
        session_id=_SESSION_ID,
        channel="cli",
        channel_scoped=False,
    )

    reminder = await reminders.create(
        instruction="Prepare coffee",
        schedule=RemindOnce(_RUN_AT),
        name="Coffee",
    )

    owner_id, values = cast(tuple[str, dict[str, object]], service.created)
    assert owner_id == _OWNER_ID
    assert values["target"] == SessionTarget(_SESSION_ID)
    assert values["schedule"] == AtSchedule(_RUN_AT)
    assert values["action"] == PromptAction("Prepare coffee")
    assert reminder.instruction == "Prepare coffee"
    assert reminder.schedule == RemindOnce(_RUN_AT)


async def test_reminders_list_is_scoped_to_its_owner() -> None:
    service = _AutomationService()
    reminders = GatewayReminders(
        _UnitOfWork(service),
        owner_id=_OWNER_ID,
        session_id=_SESSION_ID,
        channel="cli",
        channel_scoped=False,
    )

    assert await reminders.list() == ()


async def test_reminders_from_an_expiring_session_target_the_channel() -> None:
    service = _AutomationService()
    reminders = GatewayReminders(
        _UnitOfWork(service),
        owner_id=_OWNER_ID,
        session_id=_SESSION_ID,
        channel="voice",
        channel_scoped=True,
    )

    await reminders.create(
        instruction="Prepare coffee",
        schedule=RemindOnce(_RUN_AT),
    )

    _, values = cast(tuple[str, dict[str, object]], service.created)
    assert values["target"] == ChannelTarget("voice")
