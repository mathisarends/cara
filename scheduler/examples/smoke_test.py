"""Run a recurring scheduler job locally.

From the repository root:

    uv run python scheduler/examples/smoke_test.py
"""

import asyncio
import tempfile
from pathlib import Path

from scheduler import AgentPromptPayload, EverySchedule, JobDefinition, JobRunner, NoDelivery, Scheduler


class ConsoleJobRunner(JobRunner):
    """Minimal gateway adapter that visibly executes agent-prompt jobs."""

    def __init__(self, expected_runs: int) -> None:
        self._completed = asyncio.Event()
        self._expected_runs = expected_runs
        self._run_count = 0

    async def run(self, job: JobDefinition) -> None:
        self._run_count += 1
        print(f"run {self._run_count}: {job.name} — {job.payload.prompt}")
        if self._run_count == self._expected_runs:
            self._completed.set()

    async def wait_until_complete(self) -> None:
        await self._completed.wait()


async def main() -> None:
    runner = ConsoleJobRunner(expected_runs=3)
    job = JobDefinition(
        id="scheduler-smoke-test",
        name="Wiederkehrender Smoke-Test",
        schedule=EverySchedule(seconds=1),
        payload=AgentPromptPayload(prompt="Bestätige, dass der Scheduler läuft."),
        delivery=NoDelivery(),
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "jobs.sqlite"
        async with Scheduler(database_path, runner) as scheduler:
            scheduled_job = await scheduler.add(job)
            print(f"registered: {scheduled_job.id}")
            print(f"next run: {scheduled_job.next_run_at}")

            await asyncio.wait_for(runner.wait_until_complete(), timeout=6)

            active_jobs = await scheduler.list()
            print(f"stored recurring jobs: {[active_job.id for active_job in active_jobs]}")
            await scheduler.remove(job.id)
            print("removed: scheduler-smoke-test")


if __name__ == "__main__":
    asyncio.run(main())
