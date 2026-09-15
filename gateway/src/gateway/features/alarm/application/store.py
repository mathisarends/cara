import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from gateway.features.alarm.application.ports import AlarmScheduler
from gateway.features.alarm.domain import Alarm, AlarmRepository


class AlarmStore:
    """Persists alarm state and keeps the runtime timers in step with it.

    Service and execution share one store so that user commands and due runs
    never interleave between loading and saving an alarm.
    """

    def __init__(self, repository: AlarmRepository, scheduler: AlarmScheduler) -> None:
        self._repository = repository
        self._scheduler = scheduler
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def mutation(self) -> AsyncIterator[None]:
        async with self._lock:
            yield

    async def find(self, alarm_id: UUID) -> Alarm | None:
        return await self._repository.find_by_id(alarm_id)

    async def find_by_owner(self, owner_id: str) -> tuple[Alarm, ...]:
        return await self._repository.find_by_owner(owner_id)

    async def find_all(self) -> tuple[Alarm, ...]:
        return await self._repository.find_all()

    async def save(self, alarm: Alarm, now: datetime) -> Alarm:
        # Persist before arming so a due run always finds the stored alarm.
        saved = await self._repository.save(alarm)
        self._scheduler.arm(saved, now)
        return saved

    async def commit(self, alarm: Alarm, now: datetime) -> Alarm | None:
        """Save the alarm, or remove it once its last occurrence has ended."""
        if alarm.is_finished:
            await self.remove(alarm)
            return None
        return await self.save(alarm, now)

    async def remove(self, alarm: Alarm) -> None:
        self._scheduler.disarm(alarm.id)
        await self._repository.remove(alarm)

    def arm(self, alarm: Alarm, now: datetime) -> None:
        self._scheduler.arm(alarm, now)
