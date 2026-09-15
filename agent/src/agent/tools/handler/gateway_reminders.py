from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

import httpx2
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.tools.handler.ports import (
    Reminder,
    Reminders,
    ReminderSchedule,
    RemindEvery,
    RemindOnce,
    RemindOnCron,
)
from agent.tools.middleware import ToolError
from gateway_rest_client import (
    AtSchedule,
    AutomationResponse,
    AutomationSchedule,
    AutomationScheduleKind,
    AutomationTarget,
    ClientError,
    CreateAutomationRequest,
    CronSchedule,
    GatewayRestClient,
    IntervalSchedule,
    ReminderPayload,
    TransportError,
    UpdateAutomationRequest,
)


class GatewayConnection(BaseSettings):
    """Gateway base URL and the owner the agent schedules reminders for."""

    model_config = SettingsConfigDict(
        env_prefix="CARA_GATEWAY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "http://127.0.0.1:8000"
    token: SecretStr | None = None
    owner_id: str = Field(default="local", min_length=1)


class GatewayReminders(Reminders):
    """Reminders backed by the gateway automation REST API."""

    def __init__(self, connection: GatewayConnection, *, session_id: UUID) -> None:
        if connection.token is None:
            raise ValueError("A gateway token is required to schedule reminders")
        self._connection = connection
        self._token = connection.token.get_secret_value()
        self._owner_id = connection.owner_id
        self._session_id = session_id

    async def list(self) -> tuple[Reminder, ...]:
        async with self._client() as client:
            response = await client.list_automations(self._owner_id)
        return tuple(_reminder(automation) for automation in response.automations)

    async def create(
        self,
        *,
        instruction: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder:
        async with self._client() as client:
            automation = await client.create_automation(
                self._owner_id,
                CreateAutomationRequest(
                    target=AutomationTarget(session_id=self._session_id),
                    schedule=_automation_schedule(schedule),
                    payload=ReminderPayload(instruction=instruction),
                    name=name,
                ),
            )
        return _reminder(automation)

    async def update(
        self,
        reminder_id: UUID,
        *,
        instruction: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder:
        async with self._client() as client:
            automation = await client.update_automation(
                self._owner_id,
                reminder_id,
                UpdateAutomationRequest(
                    schedule=_automation_schedule(schedule),
                    payload=ReminderPayload(instruction=instruction),
                    name=name,
                ),
            )
        return _reminder(automation)

    async def delete(self, reminder_id: UUID) -> None:
        async with self._client() as client:
            await client.delete_automation(self._owner_id, reminder_id)

    @asynccontextmanager
    async def _client(self) -> AsyncGenerator[GatewayRestClient]:
        async with httpx2.AsyncClient() as http:
            client = GatewayRestClient(
                http,
                self._connection.url,
                credentials={"GatewayToken": self._token},
            )
            try:
                yield client
            except TransportError as error:
                raise ToolError(f"The gateway is unreachable: {error}") from error
            except ClientError as error:
                raise ToolError(f"The gateway rejected the request: {error}") from error


def _reminder(automation: AutomationResponse) -> Reminder:
    return Reminder(
        id=automation.id,
        instruction=automation.payload.instruction,
        schedule=_reminder_schedule(automation.schedule),
        next_run_at=automation.next_run_at,
        name=automation.name,
    )


def _reminder_schedule(schedule: AutomationSchedule) -> ReminderSchedule:
    match schedule:
        case AtSchedule(run_at=run_at):
            return RemindOnce(when=run_at)
        case IntervalSchedule(every_seconds=every_seconds):
            return RemindEvery(seconds=every_seconds)
        case CronSchedule(expression=expression, timezone=timezone):
            return RemindOnCron(expression=expression, timezone=timezone)


def _automation_schedule(schedule: ReminderSchedule) -> AutomationSchedule:
    match schedule:
        case RemindOnce(when=when):
            return AtSchedule(kind=AutomationScheduleKind.AT, run_at=when)
        case RemindEvery(seconds=seconds):
            return IntervalSchedule(
                kind=AutomationScheduleKind.INTERVAL,
                every_seconds=seconds,
                run_immediately=False,
            )
        case RemindOnCron(expression=expression, timezone=timezone):
            return CronSchedule(
                kind=AutomationScheduleKind.CRON,
                expression=expression,
                timezone=timezone,
            )
