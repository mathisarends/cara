import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any, Self
from uuid import uuid4
from zoneinfo import ZoneInfo

from croniter import croniter

from scheduler.models import (
    AgentRunner,
    AgentRunRequest,
    Cron,
    ErrorHandler,
    Heartbeat,
    Reminder,
    ScheduledJob,
    Trigger,
)

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(
        self,
        runner: AgentRunner,
        *,
        error_handler: ErrorHandler | None = None,
    ) -> None:
        self._runner = runner
        self._error_handler = error_handler
        self._jobs: dict[str, ScheduledJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def jobs(self) -> tuple[ScheduledJob, ...]:
        return tuple(self._jobs.values())

    def schedule(
        self,
        agent_id: str,
        *,
        trigger: Trigger,
        payload: Mapping[str, Any] | None = None,
        job_id: str | None = None,
        name: str | None = None,
    ) -> ScheduledJob:
        job = ScheduledJob(
            id=job_id or uuid4().hex,
            agent_id=agent_id,
            trigger=trigger,
            payload=payload or {},
            name=name,
        )
        if job.id in self._jobs:
            raise ValueError(f"A job with id {job.id!r} is already scheduled")

        self._jobs[job.id] = job
        if self._running:
            self._start_job(job)
        return job

    def heartbeat(
        self,
        agent_id: str,
        *,
        every: timedelta,
        payload: Mapping[str, Any] | None = None,
        run_immediately: bool = True,
        job_id: str | None = None,
        name: str | None = None,
    ) -> ScheduledJob:
        return self.schedule(
            agent_id,
            trigger=Heartbeat(every=every, run_immediately=run_immediately),
            payload=payload,
            job_id=job_id,
            name=name,
        )

    def reminder(
        self,
        agent_id: str,
        *,
        at: datetime | None = None,
        after: timedelta | None = None,
        payload: Mapping[str, Any] | None = None,
        job_id: str | None = None,
        name: str | None = None,
    ) -> ScheduledJob:
        if (at is None) == (after is None):
            raise ValueError("Provide exactly one of 'at' or 'after'")
        if after is not None:
            if after < timedelta(0):
                raise ValueError("Reminder delay must not be negative")
            at = datetime.now(UTC) + after
        assert at is not None
        return self.schedule(
            agent_id,
            trigger=Reminder(at=at),
            payload=payload,
            job_id=job_id,
            name=name,
        )

    def cron(
        self,
        agent_id: str,
        *,
        expression: str,
        timezone: str | tzinfo = UTC,
        payload: Mapping[str, Any] | None = None,
        job_id: str | None = None,
        name: str | None = None,
    ) -> ScheduledJob:
        resolved_timezone = (
            ZoneInfo(timezone) if isinstance(timezone, str) else timezone
        )
        return self.schedule(
            agent_id,
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

    def _start_job(self, job: ScheduledJob) -> None:
        self._tasks[job.id] = asyncio.create_task(
            self._run_job(job),
            name=f"scheduler:{job.id}",
        )

    async def _run_job(self, job: ScheduledJob) -> None:
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

    async def _dispatch(self, job: ScheduledJob, scheduled_for: datetime) -> None:
        request = AgentRunRequest(
            job_id=job.id,
            agent_id=job.agent_id,
            kind=job.kind,
            scheduled_for=scheduled_for,
            payload=job.payload,
            job_name=job.name,
        )
        try:
            await self._runner(request)
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
        case Heartbeat(run_immediately=True):
            return now
        case Heartbeat(every=every):
            return now + every
        case Reminder(at=at):
            return at.astimezone(UTC)
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
        case Heartbeat(every=every):
            next_run = previous + every
            if next_run <= now:
                missed = (now - next_run) // every + 1
                next_run += missed * every
            return next_run
        case Reminder():
            return None
        case Cron(expression=expression, timezone=timezone):
            local_now = now.astimezone(timezone)
            return croniter(expression, local_now).get_next(datetime).astimezone(UTC)


async def _sleep_until(scheduled_for: datetime) -> None:
    delay = max(0.0, (scheduled_for - datetime.now(UTC)).total_seconds())
    await asyncio.sleep(delay)
