from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from gateway.features.alarm.domain import Alarm, AlarmTarget, DueRun


class AlarmTargetResolver(ABC):
    @abstractmethod
    async def require(self, target: AlarmTarget) -> None: ...


class AlarmRunExecutor(ABC):
    @abstractmethod
    async def execute(self, alarm: Alarm, run: DueRun, now: datetime) -> None: ...


class AlarmScheduler(ABC):
    """Runtime timer for persisted alarms; it never owns their state."""

    @abstractmethod
    def arm(self, alarm: Alarm, now: datetime) -> None:
        """Replace the pending timer with the alarm's next due run or expiry."""

    @abstractmethod
    def disarm(self, alarm_id: UUID) -> None:
        """Remove the pending timer. Never cancels an agent run already started."""


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime: ...
