import asyncio
import logging
from datetime import UTC, datetime
from functools import partial

from croniter import croniter

from scheduler.models import (
    At,
    Cron,
    Interval,
    JobRunner,
    ScheduledJob,
    ScheduledRun,
    Trigger,
)

logger = logging.getLogger(__name__)


class Scheduler[PayloadT]:
    """In-memory scheduler; hosts own persistence and re-schedule on startup."""

    def __init__(self, runner: JobRunner[PayloadT]) -> None:
        self._runner = runner
        self._jobs: dict[str, ScheduledJob[PayloadT]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    def schedule(
        self,
        job_id: str,
        *,
        trigger: Trigger,
        payload: PayloadT,
        next_run_at: datetime | None = None,
    ) -> None:
        """Arm a job, replacing any job with the same id.

        Pass ``next_run_at`` to resume at a run the host persisted; a time in the
        past runs once immediately.
        """
        if next_run_at is not None and next_run_at.utcoffset() is None:
            raise ValueError("Next run time must include a timezone")
        self.remove(job_id)
        job = ScheduledJob(
            id=job_id,
            trigger=trigger,
            payload=payload,
            next_run_at=(
                first_run(trigger, datetime.now(UTC))
                if next_run_at is None
                else next_run_at
            ),
        )
        self._jobs[job_id] = job
        if self._running:
            self._start_job(job)

    def remove(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)
        task = self._tasks.pop(job_id, None)
        if task is not None:
            task.cancel()

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

    def _start_job(self, job: ScheduledJob[PayloadT]) -> None:
        task = asyncio.create_task(self._run_job(job), name=f"scheduler:{job.id}")
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
            next_run_at = _next_run(
                job.trigger,
                previous=job.next_run_at,
                now=datetime.now(UTC),
            )
            await self._dispatch(
                ScheduledRun(
                    job_id=job.id,
                    scheduled_for=job.next_run_at,
                    next_run_at=next_run_at,
                    payload=job.payload,
                )
            )
            if next_run_at is None:
                if self._jobs.get(job.id) is job:
                    del self._jobs[job.id]
                return
            job.next_run_at = next_run_at

    async def _dispatch(self, run: ScheduledRun[PayloadT]) -> None:
        try:
            await self._runner(run)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled job %s failed", run.job_id)


def first_run(trigger: Trigger, now: datetime) -> datetime:
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
