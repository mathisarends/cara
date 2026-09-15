from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from gateway.features.automation.application import (
    AutomationExecution,
    AutomationScheduler,
    AutomationService,
)
from gateway.features.automation.domain import (
    AtSchedule,
    Automation,
    AutomationSchedule,
    CronSchedule,
    IntervalSchedule,
)
from gateway.shared.unit_of_work import UnitOfWork
from scheduler import At, Cron, Interval, ScheduledRun, Scheduler, Trigger, first_run


class InProcessAutomationScheduler(AutomationScheduler):
    def __init__(self, scheduler: Scheduler[UUID]) -> None:
        self._scheduler = scheduler

    def first_run_at(self, schedule: AutomationSchedule) -> datetime:
        return first_run(_to_trigger(schedule), datetime.now(UTC))

    def arm(self, automation: Automation) -> None:
        self._scheduler.schedule(
            str(automation.id),
            trigger=_to_trigger(automation.schedule),
            payload=automation.id,
            next_run_at=automation.next_run_at,
        )

    def disarm(self, automation: Automation) -> None:
        self._scheduler.remove(str(automation.id))


class AutomationJobRunner:
    def __init__(self, unit_of_work: UnitOfWork[AutomationExecution]) -> None:
        self._unit_of_work = unit_of_work

    async def __call__(self, run: ScheduledRun[UUID]) -> None:
        async with self._unit_of_work() as execution:
            await execution.run(
                run.payload,
                scheduled_for=run.scheduled_for,
                next_run_at=run.next_run_at,
            )


class AutomationRuntime:
    def __init__(
        self,
        scheduler: Scheduler[UUID],
        unit_of_work: UnitOfWork[AutomationService],
    ) -> None:
        self._scheduler = scheduler
        self._unit_of_work = unit_of_work

    async def start(self) -> None:
        await self._scheduler.start()
        try:
            async with self._unit_of_work() as service:
                await service.resume()
        except BaseException:
            await self._scheduler.stop()
            raise

    async def stop(self) -> None:
        await self._scheduler.stop()


def _to_trigger(schedule: AutomationSchedule) -> Trigger:
    match schedule:
        case AtSchedule(run_at=run_at):
            return At(when=run_at)
        case IntervalSchedule(every=every, run_immediately=run_immediately):
            return Interval(every=every, run_immediately=run_immediately)
        case CronSchedule(expression=expression, timezone=timezone):
            return Cron(expression=expression, timezone=ZoneInfo(timezone))
