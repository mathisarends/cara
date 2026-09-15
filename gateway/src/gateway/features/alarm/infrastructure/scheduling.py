from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import count
from uuid import UUID

from gateway.features.alarm.application import (
    AlarmExecution,
    AlarmScheduler,
    Clock,
)
from gateway.features.alarm.domain import Alarm, DueRun
from scheduler import At, ScheduledRun, Scheduler


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class _Expiry:
    alarm_id: UUID
    due_at: datetime


type _AlarmJob = DueRun | _Expiry


class InProcessAlarmScheduler(AlarmScheduler):
    """Arms exactly one one-shot timer per alarm on the in-memory scheduler.

    Every armed timer gets a fresh job id: ``Scheduler.schedule`` cancels a
    running task with the same id, and a due run re-arms its own alarm.
    """

    def __init__(self) -> None:
        self._scheduler: Scheduler[_AlarmJob] = Scheduler(self._run)
        self._armed: dict[UUID, str] = {}
        self._sequence = count()
        self._execution: AlarmExecution | None = None

    async def start(self, execution: AlarmExecution) -> None:
        self._execution = execution
        await self._scheduler.start()

    async def stop(self) -> None:
        await self._scheduler.stop()

    def arm(self, alarm: Alarm, now: datetime) -> None:
        self.disarm(alarm.id)
        job = _next_job(alarm, now)
        if job is None:
            return
        job_id = f"alarm:{alarm.id}:{_label(job)}:{next(self._sequence)}"
        self._scheduler.schedule(job_id, trigger=At(when=job.due_at), payload=job)
        self._armed[alarm.id] = job_id

    def disarm(self, alarm_id: UUID) -> None:
        job_id = self._armed.pop(alarm_id, None)
        if job_id is not None:
            self._scheduler.remove(job_id)

    async def _run(self, run: ScheduledRun[_AlarmJob]) -> None:
        if self._execution is None:
            raise RuntimeError("The alarm scheduler has not been started")
        job = run.payload
        # A started run is no longer pending, so disarming never cancels it.
        if self._armed.get(job.alarm_id) == run.job_id:
            del self._armed[job.alarm_id]
        match job:
            case DueRun():
                await self._execution.run(job)
            case _Expiry(alarm_id=alarm_id):
                await self._execution.expire_due(alarm_id)


def _next_job(alarm: Alarm, now: datetime) -> _AlarmJob | None:
    if (run := alarm.next_due_run(now)) is not None:
        return run
    if (expires_at := alarm.expires_at) is not None:
        return _Expiry(alarm.id, expires_at)
    return None


def _label(job: _AlarmJob) -> str:
    match job:
        case DueRun(phase=phase, due_at=due_at):
            return f"{phase}:{due_at.isoformat()}"
        case _Expiry(due_at=due_at):
            return f"expiry:{due_at.isoformat()}"
