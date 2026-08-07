import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo

from apscheduler.job import Job
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from scheduler.models import AtSchedule, CronSchedule, EverySchedule, JobDefinition, ScheduledJob
from scheduler.store import JobStore

logger = logging.getLogger(__name__)


class JobRunner(ABC):
    """Gateway-owned adapter that interprets a declarative job."""

    @abstractmethod
    async def run(self, job: JobDefinition) -> None:
        """Interpret and execute *job*."""


class Scheduler:
    """Persistent scheduler for agent-authored job declarations."""

    def __init__(
        self,
        database_path: str | Path,
        runner: JobRunner,
        *,
        timezone: str = "UTC",
    ) -> None:
        self._store = JobStore(database_path)
        self._runner = runner
        self._timezone = ZoneInfo(timezone)
        self._scheduler = AsyncIOScheduler(
            timezone=self._timezone,
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        )

    @property
    def running(self) -> bool:
        return self._scheduler.running

    async def start(self) -> None:
        if self.running:
            return

        await self._store.open()
        self._scheduler.start(paused=True)
        for job in await self._store.list():
            if job.enabled:
                self._register(job)
        self._scheduler.resume()

    async def shutdown(self) -> None:
        if self.running:
            self._scheduler.shutdown(wait=True)
            await asyncio.sleep(0)
        await self._store.close()

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.shutdown()

    async def add(self, job: JobDefinition, *, replace_existing: bool = False) -> ScheduledJob:
        self._require_running()
        trigger = _create_trigger(job)
        await self._store.add(job, replace_existing=replace_existing)

        if job.enabled:
            self._scheduler.add_job(
                self._run,
                trigger=trigger,
                id=job.id,
                args=(job.id,),
                name=job.name,
                replace_existing=replace_existing,
            )
        else:
            self._remove_runtime_job(job.id)
        return self._to_scheduled_job(job)

    async def get(self, job_id: str) -> ScheduledJob | None:
        self._require_running()
        job = await self._store.get(job_id)
        return self._to_scheduled_job(job) if job is not None else None

    async def list(self, *, include_disabled: bool = False) -> list[ScheduledJob]:
        self._require_running()
        jobs = await self._store.list()
        if not include_disabled:
            jobs = [job for job in jobs if job.enabled]
        return [self._to_scheduled_job(job) for job in jobs]

    async def remove(self, job_id: str) -> bool:
        self._require_running()
        removed = await self._store.remove(job_id)
        self._remove_runtime_job(job_id)
        return removed

    async def enable(self, job_id: str) -> ScheduledJob | None:
        return await self._set_enabled(job_id, enabled=True)

    async def disable(self, job_id: str) -> ScheduledJob | None:
        return await self._set_enabled(job_id, enabled=False)

    async def run_now(self, job_id: str) -> bool:
        self._require_running()
        job = await self._store.get(job_id)
        if job is None:
            return False
        self._scheduler.add_job(self._run, args=(job_id,))
        return True

    async def _set_enabled(self, job_id: str, *, enabled: bool) -> ScheduledJob | None:
        self._require_running()
        job = await self._store.get(job_id)
        if job is None:
            return None

        updated = job.model_copy(update={"enabled": enabled})
        await self._store.add(updated, replace_existing=True)
        if enabled:
            self._register(updated)
        else:
            self._remove_runtime_job(job_id)
        return self._to_scheduled_job(updated)

    async def _run(self, job_id: str) -> None:
        job = await self._store.get(job_id)
        if job is None or not job.enabled:
            return

        try:
            await self._runner.run(job)
        except Exception:
            logger.exception("Scheduled job %s failed", job_id)
            return

        if isinstance(job.schedule, AtSchedule):
            await self._store.remove(job_id)

    def _register(self, job: JobDefinition) -> None:
        self._scheduler.add_job(
            self._run,
            trigger=_create_trigger(job),
            id=job.id,
            args=(job.id,),
            name=job.name,
            replace_existing=True,
        )

    def _remove_runtime_job(self, job_id: str) -> None:
        if self._scheduler.get_job(job_id) is not None:
            self._scheduler.remove_job(job_id)

    def _to_scheduled_job(self, definition: JobDefinition) -> ScheduledJob:
        runtime_job = self._scheduler.get_job(definition.id)
        return ScheduledJob(
            **definition.model_dump(),
            next_run_at=_next_run_at(runtime_job),
        )

    def _require_running(self) -> None:
        if not self.running:
            raise RuntimeError("scheduler must be started first")


def _create_trigger(job: JobDefinition) -> DateTrigger | IntervalTrigger | CronTrigger:
    schedule = job.schedule
    if isinstance(schedule, AtSchedule):
        return DateTrigger(run_date=schedule.at)
    if isinstance(schedule, EverySchedule):
        return IntervalTrigger(seconds=schedule.seconds)
    if isinstance(schedule, CronSchedule):
        return CronTrigger.from_crontab(schedule.expression, timezone=ZoneInfo(schedule.timezone))
    raise TypeError(f"unsupported schedule: {type(schedule).__name__}")


def _next_run_at(job: Job | None) -> datetime | None:
    return job.next_run_time if job is not None else None
