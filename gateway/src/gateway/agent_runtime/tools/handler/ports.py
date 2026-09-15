from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RemindOnce:
    when: datetime


@dataclass(frozen=True, slots=True)
class RemindEvery:
    seconds: float


@dataclass(frozen=True, slots=True)
class RemindOnCron:
    expression: str
    timezone: str


type ReminderSchedule = RemindOnce | RemindEvery | RemindOnCron


@dataclass(frozen=True, slots=True)
class Reminder:
    id: UUID
    instruction: str
    schedule: ReminderSchedule
    next_run_at: datetime
    name: str | None = None


class Reminders(ABC):
    """Scheduled reminders for the conversation the agent is currently in.

    Implementations are bound to one session and turn, so the agent can only
    ever reach the reminders of the conversation it is running in.
    """

    @abstractmethod
    async def list(self) -> tuple[Reminder, ...]: ...

    @abstractmethod
    async def create(
        self,
        *,
        instruction: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder: ...

    @abstractmethod
    async def update(
        self,
        reminder_id: UUID,
        *,
        instruction: str,
        schedule: ReminderSchedule,
        name: str | None = None,
    ) -> Reminder: ...

    @abstractmethod
    async def delete(self, reminder_id: UUID) -> None: ...
