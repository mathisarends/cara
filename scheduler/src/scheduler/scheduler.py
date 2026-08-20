import asyncio
import logging
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Self
from uuid import uuid4
from zoneinfo import ZoneInfo

from croniter import croniter

from scheduler.models import (
    At,
    Cron,
    ErrorHandler,
    Interval,
    JobRunner,
    ScheduledJob,
    ScheduledRun,
    Trigger,
)

logger = logging.getLogger(__name__)


class Scheduler[PayloadT]:
    def __init__(
        self,
        runner: JobRunner[PayloadT],
        *,
        error_handler: ErrorHandler[PayloadT] | None = None,
    ) -> None:
        self._runner = runner
        self._error_handler = error_handler
        self._jobs: dict[str, ScheduledJob[PayloadT]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def jobs(self) -> tuple[ScheduledJob[PayloadT], ...]:
        return tuple(self._jobs.values())

    def schedule(
        self,
        *,
        trigger: Trigger,
        payload: PayloadT,
        job_id: str | None = None,
        name: str | None = None,
    ) -> ScheduledJob[PayloadT]:
        job = ScheduledJob(
            id=job_id or uuid4().hex,
            trigger=trigger,
            payload=payload,
            name=name,
        )
        if job.id in self._jobs:
            raise ValueError(f"A job with id {job.id!r} is already scheduled")

        self._jobs[job.id] = job
        if self._running:
            self._start_job(job)
        return job

    def at(
        self,
        when: datetime,
        *,
        payload: PayloadT,
        job_id: str | None = None,
        name: str | None = None,
    ) -> ScheduledJob[PayloadT]:
        return self.schedule(
            trigger=At(when=when),
            payload=payload,
            job_id=job_id,
            name=name,
        )

    def interval(
        self,
        *,
        every: timedelta,
        payload: PayloadT,
        run_immediately: bool = True,
        job_id: str | None = None,
        name: str | None = None,
    ) -> ScheduledJob[PayloadT]:
        return self.schedule(
            trigger=Interval(every=every, run_immediately=run_immediately),
            payload=payload,
            job_id=job_id,
            name=name,
        )

    def cron(
        self,
        *,
        expression: str,
        timezone: str | tzinfo = UTC,
        payload: PayloadT,
        job_id: str | None = None,
        name: str | None = None,
    ) -> ScheduledJob[PayloadT]:
        resolved_timezone = (
            ZoneInfo(timezone) if isinstance(timezone, str) else timezone
        )
        return self.schedule(
            trigger=Cron(expression=expression, timezone=resolved_timezone),
            payload=payload,
            job_id=job_id,
            name=name,
        )

    def remove(self, job_id: str) -> bool:
        job = self._jobs.pop(job_id, None)
        if job is None:
            return False
        task = self._tasks.pop(job_id, None)
        if task is not None:
            task.cancel()
        return True

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for job in self._jobs.values():
            self._start_job(job)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        tasks = tuple(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.stop()

    def _start_job(self, job: ScheduledJob[PayloadT]) -> None:
        self._tasks[job.id] = asyncio.create_task(
            self._run_job(job),
            name=f"scheduler:{job.id}",
        )

    async def _run_job(self, job: ScheduledJob[PayloadT]) -> None:
        scheduled_for = _first_run(job.trigger, datetime.now(UTC))
        while scheduled_for is not None:
            await _sleep_until(scheduled_for)
            if job.id not in self._jobs:
                return
            await self._dispatch(job, scheduled_for)
            scheduled_for = _next_run(
                job.trigger,
                previous=scheduled_for,
                now=datetime.now(UTC),
            )
        self._jobs.pop(job.id, None)
        self._tasks.pop(job.id, None)

    async def _dispatch(
        self,
        job: ScheduledJob[PayloadT],
        scheduled_for: datetime,
    ) -> None:
        run = ScheduledRun(
            job_id=job.id,
            kind=job.kind,
            scheduled_for=scheduled_for,
            payload=job.payload,
            job_name=job.name,
        )
        try:
            await self._runner(run)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Scheduled job %s failed", job.id)
            if self._error_handler is not None:
                try:
                    await self._error_handler(job, error)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "Error handler failed for scheduled job %s", job.id
                    )


def _first_run(trigger: Trigger, now: datetime) -> datetime:
    match trigger:
        case At(when=when):
            return when.astimezone(UTC)
        case Interval(run_immediately=True):
            return now
        case Interval(every=every):
            return now + every
        case Cron(expression=expression, timezone=timezone):
            local_now = now.astimezone(timezone)
            return croniter(expression, local_now).get_next(datetime).astimezone(UTC)


def _next_run(
    trigger: Trigger,
    *,
    previous: datetime,
    now: datetime,
) -> datetime | None:
    match trigger:
        case At():
            return None
        case Interval(every=every):
            next_run = previous + every
            if next_run <= now:
                missed = (now - next_run) // every + 1
                next_run += missed * every
            return next_run
        case Cron(expression=expression, timezone=timezone):
            local_now = now.astimezone(timezone)
            return croniter(expression, local_now).get_next(datetime).astimezone(UTC)


async def _sleep_until(scheduled_for: datetime) -> None:
    delay = max(0.0, (scheduled_for - datetime.now(UTC)).total_seconds())
    await asyncio.sleep(delay)
