import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from features.alarm.fakes import DAILY_AT_SIX, AcceptAllTargets, find_alarm, save_alarm
from gateway.features.alarm.application import (
    AlarmExecution,
    AlarmRunExecutor,
    AlarmService,
    AlarmStore,
)
from gateway.features.alarm.domain import (
    Alarm,
    AlarmPhase,
    AlarmRepository,
    AlarmRoutine,
    DueRun,
    Occurrence,
    OccurrenceState,
    OnceRecurrence,
    SessionTarget,
)
from gateway.features.alarm.infrastructure.scheduling import (
    InProcessAlarmScheduler,
    SystemClock,
)
from gateway.shared import UnitOfWork


class _SlowExecutor(AlarmRunExecutor):
    def __init__(self) -> None:
        self.started: list[AlarmPhase] = []
        self.completed: list[AlarmPhase] = []
        self.release = asyncio.Event()
        self.release.set()

    async def execute(self, alarm: Alarm, run: DueRun, now: datetime) -> None:
        self.started.append(run.phase)
        await asyncio.sleep(0.05)
        await self.release.wait()
        self.completed.append(run.phase)


async def test_phases_run_in_order_while_each_run_rearms_its_alarm(
    alarm_repositories: UnitOfWork[AlarmRepository],
) -> None:
    executor = _SlowExecutor()
    scheduler, service = await _start(alarm_repositories, executor)
    try:
        alarm = await service.create(
            "owner",
            target=SessionTarget(uuid4()),
            recurrence=OnceRecurrence(datetime.now(UTC) + timedelta(milliseconds=300)),
            routine=AlarmRoutine("wake-up"),
            pre_wake_lead=timedelta(minutes=30),
        )
        await _until(
            lambda: executor.completed == [AlarmPhase.PRE_WAKE, AlarmPhase.WAKE]
        )

        await service.snooze(alarm.id, "owner", timedelta(milliseconds=100))
        await _until(lambda: AlarmPhase.SNOOZE_END in executor.completed)

        dismissed = await service.dismiss(alarm.id, "owner")
    finally:
        await scheduler.stop()

    assert executor.completed == [
        AlarmPhase.PRE_WAKE,
        AlarmPhase.WAKE,
        AlarmPhase.SNOOZE_END,
    ]
    assert dismissed is None
    assert await find_alarm(alarm_repositories, alarm.id) is None


async def test_disarming_never_cancels_a_running_routine(
    alarm_repositories: UnitOfWork[AlarmRepository],
) -> None:
    executor = _SlowExecutor()
    executor.release.clear()
    scheduler, service = await _start(alarm_repositories, executor)
    try:
        alarm = await service.create(
            "owner",
            target=SessionTarget(uuid4()),
            recurrence=OnceRecurrence(datetime.now(UTC) + timedelta(milliseconds=50)),
            routine=AlarmRoutine("wake-up"),
        )
        await _until(lambda: executor.started == [AlarmPhase.WAKE])

        await service.delete(alarm.id, "owner")
        executor.release.set()
        await _until(lambda: executor.completed == [AlarmPhase.WAKE])
    finally:
        await scheduler.stop()


async def test_resume_honours_the_grace_period_for_overdue_runs(
    alarm_repositories: UnitOfWork[AlarmRepository],
) -> None:
    now = datetime.now(UTC)
    recent = await save_alarm(alarm_repositories, _overdue(now - timedelta(minutes=5)))
    missed = await save_alarm(alarm_repositories, _overdue(now - timedelta(minutes=20)))
    executor = _SlowExecutor()

    scheduler, _ = await _start(alarm_repositories, executor)
    try:
        await _until(lambda: executor.completed == [AlarmPhase.WAKE])
        await _until_stored(
            alarm_repositories,
            missed,
            lambda occurrence: (
                occurrence.state is OccurrenceState.UPCOMING
                and occurrence.wake_at > now
            ),
        )
    finally:
        await scheduler.stop()

    stored = await find_alarm(alarm_repositories, recent.id)
    assert stored is not None
    assert stored.occurrence is not None
    assert stored.occurrence.state is OccurrenceState.ACTIVE


async def _start(
    repositories: UnitOfWork[AlarmRepository],
    executor: AlarmRunExecutor,
) -> tuple[InProcessAlarmScheduler, AlarmService]:
    scheduler = InProcessAlarmScheduler()
    store = AlarmStore(repositories, scheduler)
    clock = SystemClock()
    service = AlarmService(store, AcceptAllTargets(), clock)
    await service.resume()
    await scheduler.start(AlarmExecution(store, executor, clock))
    return scheduler, service


def _overdue(wake_at: datetime) -> Alarm:
    return Alarm(
        id=uuid4(),
        created_at=wake_at - timedelta(days=1),
        owner_id="owner",
        target=SessionTarget(uuid4()),
        recurrence=DAILY_AT_SIX,
        routine=AlarmRoutine("wake-up"),
        occurrence=Occurrence(wake_at, OccurrenceState.UPCOMING),
    )


async def _until(predicate: Callable[[], bool]) -> None:
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.01)


async def _until_stored(
    repositories: UnitOfWork[AlarmRepository],
    alarm: Alarm,
    predicate: Callable[[Occurrence], bool],
) -> None:
    async with asyncio.timeout(2):
        while True:
            stored = await find_alarm(repositories, alarm.id)
            if stored and stored.occurrence and predicate(stored.occurrence):
                return
            await asyncio.sleep(0.01)
