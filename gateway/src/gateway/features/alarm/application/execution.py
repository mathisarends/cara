import logging
from uuid import UUID

from gateway.features.alarm.application.ports import AlarmRunExecutor, Clock
from gateway.features.alarm.application.store import AlarmStore
from gateway.features.alarm.domain import MISSED_GRACE, AlarmPhase, DueRun

logger = logging.getLogger(__name__)


class AlarmExecution:
    def __init__(
        self,
        store: AlarmStore,
        executor: AlarmRunExecutor,
        clock: Clock,
    ) -> None:
        self._store = store
        self._executor = executor
        self._clock = clock

    async def run(self, run: DueRun) -> None:
        async with self._store.mutation():
            alarm = await self._store.find(run.alarm_id)
            now = self._clock.now()
            if alarm is None or not alarm.is_due(run, now):
                return
            if run.phase is AlarmPhase.PRE_WAKE and now >= run.wake_at:
                # Too late for a lead: enter pre-wake silently so the wake run follows.
                alarm.start_run(run, now)
                await self._store.save(alarm, now)
                return
            if run.phase is not AlarmPhase.PRE_WAKE and now - run.due_at > MISSED_GRACE:
                logger.warning(
                    "Alarm %s missed its %s run due at %s",
                    alarm.id,
                    run.phase,
                    run.due_at.isoformat(),
                )
                alarm.expire(now)
                await self._store.commit(alarm, now)
                return
            alarm.start_run(run, now)
            # Persisting before the agent run keeps each phase at most once.
            alarm = await self._store.save(alarm, now)
        try:
            await self._executor.execute(alarm, run, now)
        except Exception:
            logger.exception(
                "Alarm %s failed to run its %s routine", alarm.id, run.phase
            )

    async def expire_due(self, alarm_id: UUID) -> None:
        async with self._store.mutation():
            alarm = await self._store.find(alarm_id)
            now = self._clock.now()
            if alarm is None or alarm.next_due_run(now) is not None:
                return
            expires_at = alarm.expires_at
            if expires_at is None or now < expires_at:
                return
            logger.info(
                "Alarm %s closed its occurrence after the active timeout", alarm.id
            )
            alarm.expire(now)
            await self._store.commit(alarm, now)
