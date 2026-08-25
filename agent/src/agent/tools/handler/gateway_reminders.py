from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from pyrpckit.client import RpcClientError

from agent.tools.handler.ports import (
    Reminder,
    Reminders,
    ReminderSchedule,
    RemindEvery,
    RemindOnce,
    RemindOnCron,
)
from agent.tools.middleware import ToolError
from gateway_client import GatewayClient, WebSocketTransport
from gateway_client.models import (
    AtSchedule,
    AutomationResponse,
    AutomationSchedule,
    CronSchedule,
    IntervalSchedule,
    ReminderAutomationPayload,
)


class GatewayConnection(BaseSettings):
    """Gateway WebSocket endpoint the agent schedules its reminders through."""

    model_config = SettingsConfigDict(
        env_prefix="CARA_GATEWAY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "ws://127.0.0.1:8000/v1/gateway"
    token: SecretStr | None = None


class GatewayReminders(Reminders):
    """Reminders backed by the gateway automation API over its typed client."""

    def __init__(
        self,
        connection: GatewayConnection,
        *,
        session_id: UUID,
        turn_id: UUID,
    ) -> None:
        if connection.token is None:
            raise ValueError("A gateway token is required to schedule reminders")
        self._connection = connection
        self._token = connection.token.get_secret_value()
        self._session_id = session_id
        self._turn_id = turn_id

    async def list(self) -> tuple[Reminder, ...]:
        async with self._client() as client:
            response = await client.automation.list(session_id=self._session_id)
        return tuple(_reminder(automation) for automation in response.automations)

    async def create(
        self,
        *,
        message: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder:
        async with self._client() as client:
            automation = await client.automation.create(
                session_id=self._session_id,
                schedule=_automation_schedule(schedule),
                payload=self._payload(message),
                name=name,
            )
        return _reminder(automation)

    async def update(
        self,
        reminder_id: str,
        *,
        message: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder:
        async with self._client() as client:
            automation = await client.automation.update(
                session_id=self._session_id,
                automation_id=reminder_id,
                schedule=_automation_schedule(schedule),
                payload=self._payload(message),
                name=name,
            )
        return _reminder(automation)

    async def delete(self, reminder_id: str) -> None:
        async with self._client() as client:
            await client.automation.delete(
                session_id=self._session_id,
                automation_id=reminder_id,
            )

    def _payload(self, message: str) -> ReminderAutomationPayload:
        return ReminderAutomationPayload(
            kind="reminder",
            message=message,
            created_from_turn_id=self._turn_id,
        )

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[GatewayClient]:
        try:
            transport = await WebSocketTransport.connect(
                self._connection.url,
                token=self._token,
            )
        except OSError as error:
            raise ToolError(f"The gateway is unreachable: {error}") from error
        try:
            async with GatewayClient(transport) as client:
                yield client
        except RpcClientError as error:
            raise ToolError(f"The gateway rejected the request: {error}") from error


def _reminder(automation: AutomationResponse) -> Reminder:
    return Reminder(
        id=automation.id,
        message=automation.payload.message,
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
            return AtSchedule(run_at=when)
        case RemindEvery(seconds=seconds):
            return IntervalSchedule(every_seconds=seconds, run_immediately=False)
        case RemindOnCron(expression=expression, timezone=timezone):
            return CronSchedule(expression=expression, timezone=timezone)
