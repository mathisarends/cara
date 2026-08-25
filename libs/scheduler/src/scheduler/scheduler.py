import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta, tzinfo
from functools import partial
from typing import Self
from uuid import uuid4
from zoneinfo import ZoneInfo

from croniter import croniter

from scheduler.models import (
    At,
    Cron,
    ErrorHandler,
    Interval,
    ScheduledJob,
    ScheduledRun,
    Trigger,
)
from scheduler.ports import JobRunner, JobStore

logger = logging.getLogger(__name__)


class Scheduler[PayloadT]:
    def __init__(
        self,
        runner: JobRunner[PayloadT],
        store: JobStore[PayloadT],
        *,
        error_handler: ErrorHandler[PayloadT] | None = None,
    ) -> None:
        self._runner = runner
        self._store = store
        self._error_handler = error_handler
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    async def schedule(
        self,
        *,
        trigger: Trigger,
        payload: PayloadT,
        job_id: str | None = None,
        name: str | None = None,
    ) -> ScheduledJob[PayloadT]:
        created_at = datetime.now(UTC)
        job = ScheduledJob(
            id=job_id or uuid4().hex,
            trigger=trigger,
            payload=payload,
            created_at=created_at,
            next_run_at=_first_run(trigger, created_at),
            name=name,
        )
        async with self._lock:
            await self._store.add(job)
            if self._running:
                self._start_job(job)
        return job

    async def at(
        self,
        when: datetime,
        *,
        payload: PayloadT,
        job_id: str | None = None,
        name: str | None = None,
    ) -> ScheduledJob[PayloadT]:
        return await self.schedule(
            trigger=At(when=when),
            payload=payload,
            job_id=job_id,
            name=name,
        )

    async def interval(
        self,
        *,
        every: timedelta,
        payload: PayloadT,
        run_immediately: bool = True,
        job_id: str | None = None,
        name: str | None = None,
    ) -> ScheduledJob[PayloadT]:
        return await self.schedule(
            trigger=Interval(every=every, run_immediately=run_immediately),
            payload=payload,
            job_id=job_id,
            name=name,
        )

    async def cron(
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
        return await self.schedule(
            trigger=Cron(expression=expression, timezone=resolved_timezone),
            payload=payload,
            job_id=job_id,
            name=name,
        )

    async def update(
        self,
        job_id: str,
        *,
        trigger: Trigger,
        payload: PayloadT,
        name: str | None = None,
    ) -> ScheduledJob[PayloadT] | None:
        async with self._lock:
            existing = await self._store.get(job_id)
            if existing is None:
                return None
            job = replace(
                existing,
                trigger=trigger,
                payload=payload,
                name=name,
                next_run_at=_first_run(trigger, datetime.now(UTC)),
            )
            await self._store.update(job)
            task = self._tasks.pop(job_id, None)
            if task is not None:
                task.cancel()
            if self._running:
                self._start_job(job)
            return job

    async def remove(self, job_id: str) -> bool:
        async with self._lock:
            removed = await self._store.remove(job_id)
            task = self._tasks.pop(job_id, None)
            if task is not None:
                task.cancel()
            return removed

    async def get(self, job_id: str) -> ScheduledJob[PayloadT] | None:
        async with self._lock:
            return await self._store.get(job_id)

    async def list(self) -> tuple[ScheduledJob[PayloadT], ...]:
        async with self._lock:
            return await self._store.list()

    async def start(self) -> None:
        async with self._lock:
            if self._running:
                return
            jobs = await self._store.list()
            self._running = True
            for job in jobs:
                self._start_job(job)

    async def stop(self) -> None:
        async with self._lock:
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
        if job.id in self._tasks:
            return
        task = asyncio.create_task(
            self._run_job(job),
            name=f"scheduler:{job.id}",
        )
        self._tasks[job.id] = task
        task.add_done_callback(partial(self._job_finished, job.id))

    def _job_finished(self, job_id: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(job_id) is task:
            self._tasks.pop(job_id)
        if task.cancelled():
            return
        if error := task.exception():
            logger.error(
                "Scheduler task for job %s stopped unexpectedly",
                job_id,
                exc_info=(type(error), error, error.__traceback__),
            )

    async def _run_job(self, job: ScheduledJob[PayloadT]) -> None:
        while True:
            await _sleep_until(job.next_run_at)
            await self._dispatch(job, job.next_run_at)
            next_run_at = _next_run(
                job.trigger,
                previous=job.next_run_at,
                now=datetime.now(UTC),
            )
            if next_run_at is None:
                await self._store.remove(job.id)
                return
            job = replace(job, next_run_at=next_run_at)
            await self._store.update(job)

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
