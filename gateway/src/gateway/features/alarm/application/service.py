from datetime import timedelta
from uuid import UUID

from gateway.features.alarm.application.ports import AlarmTargetResolver, Clock
from gateway.features.alarm.application.store import AlarmStore
from gateway.features.alarm.domain import (
    Alarm,
    AlarmNotFoundError,
    AlarmRecurrence,
    AlarmRoutine,
    AlarmTarget,
)
from gateway.shared import VoiceDelivery


class AlarmService:
    def __init__(
        self,
        store: AlarmStore,
        targets: AlarmTargetResolver,
        clock: Clock,
    ) -> None:
        self._store = store
        self._targets = targets
        self._clock = clock

    async def list(self, owner_id: str) -> tuple[Alarm, ...]:
        return await self._store.find_by_owner(owner_id)

    async def get(self, alarm_id: UUID, owner_id: str) -> Alarm:
        alarm = await self._store.find(alarm_id)
        if alarm is None:
            raise AlarmNotFoundError(alarm_id)
        alarm.require_owner(owner_id)
        return alarm

    async def create(
        self,
        owner_id: str,
        *,
        target: AlarmTarget,
        recurrence: AlarmRecurrence,
        routine: AlarmRoutine,
        pre_wake_lead: timedelta | None = None,
        name: str | None = None,
        delivery: VoiceDelivery | None = None,
    ) -> Alarm:
        await self._targets.require(target)
        async with self._store.mutation():
            now = self._clock.now()
            alarm = Alarm.create(
                owner_id=owner_id,
                target=target,
                recurrence=recurrence,
                routine=routine,
                now=now,
                pre_wake_lead=pre_wake_lead,
                name=name,
                delivery=delivery,
            )
            return await self._store.save(alarm, now)

    async def update(
        self,
        alarm_id: UUID,
        owner_id: str,
        *,
        recurrence: AlarmRecurrence,
        routine: AlarmRoutine,
        pre_wake_lead: timedelta | None = None,
        name: str | None = None,
        delivery: VoiceDelivery | None = None,
    ) -> Alarm:
        async with self._store.mutation():
            alarm = await self.get(alarm_id, owner_id)
            now = self._clock.now()
            alarm.update(
                recurrence=recurrence,
                routine=routine,
                now=now,
                pre_wake_lead=pre_wake_lead,
                name=name,
                delivery=delivery,
            )
            return await self._store.save(alarm, now)

    async def delete(self, alarm_id: UUID, owner_id: str) -> None:
        async with self._store.mutation():
            alarm = await self.get(alarm_id, owner_id)
            await self._store.remove(alarm)

    async def set_enabled(self, alarm_id: UUID, owner_id: str, enabled: bool) -> Alarm:
        async with self._store.mutation():
            alarm = await self.get(alarm_id, owner_id)
            now = self._clock.now()
            alarm.set_enabled(enabled, now)
            return await self._store.save(alarm, now)

    async def skip_next(self, alarm_id: UUID, owner_id: str) -> Alarm:
        async with self._store.mutation():
            alarm = await self.get(alarm_id, owner_id)
            alarm.skip_next()
            return await self._store.save(alarm, self._clock.now())

    async def snooze(
        self,
        alarm_id: UUID,
        owner_id: str,
        duration: timedelta,
    ) -> Alarm:
        async with self._store.mutation():
            alarm = await self.get(alarm_id, owner_id)
            now = self._clock.now()
            alarm.snooze(duration, now)
            return await self._store.save(alarm, now)

    async def dismiss(self, alarm_id: UUID, owner_id: str) -> Alarm | None:
        """Dismiss the current occurrence; ``None`` once a one-time alarm is gone."""
        async with self._store.mutation():
            alarm = await self.get(alarm_id, owner_id)
            now = self._clock.now()
            alarm.dismiss(now)
            return await self._store.commit(alarm, now)

    async def resume(self) -> None:
        now = self._clock.now()
        for alarm in await self._store.find_all():
            self._store.arm(alarm, now)
