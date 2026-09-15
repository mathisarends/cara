from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

from gateway.features.alarm.application import (
    AlarmRunExecutor,
    AlarmScheduler,
    AlarmTargetResolver,
    Clock,
)
from gateway.features.alarm.domain import (
    Alarm,
    AlarmRecurrence,
    AlarmRepository,
    AlarmRoutine,
    AlarmTarget,
    DueRun,
    Occurrence,
    OnceRecurrence,
    SessionTarget,
    Weekday,
    WeeklyRecurrence,
)
from gateway.shared import UnitOfWork

# Tuesday 2026-09-15, 22:00 in Berlin.
NOW = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)
# The next daily 06:00 wake time in Berlin after NOW.
NEXT_WAKE = datetime(2026, 9, 16, 4, 0, tzinfo=UTC)
DAILY_AT_SIX = WeeklyRecurrence(
    days=frozenset(Weekday),
    local_time=time(6, 0),
    timezone="Europe/Berlin",
)


class FixedClock(Clock):
    def __init__(self, now: datetime = NOW) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


class AcceptAllTargets(AlarmTargetResolver):
    async def require(self, target: AlarmTarget) -> None:
        pass


class RecordingScheduler(AlarmScheduler):
    def __init__(self) -> None:
        self.armed: dict[UUID, DueRun | None] = {}

    def arm(self, alarm: Alarm, now: datetime) -> None:
        self.armed[alarm.id] = alarm.next_due_run(now)

    def disarm(self, alarm_id: UUID) -> None:
        self.armed.pop(alarm_id, None)


class RecordingExecutor(AlarmRunExecutor):
    def __init__(
        self,
        repositories: UnitOfWork[AlarmRepository] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.executed: list[DueRun] = []
        # The occurrence stored at the moment each run started executing.
        self.stored: list[Occurrence | None] = []
        self._repositories = repositories
        self._error = error

    async def execute(self, alarm: Alarm, run: DueRun, now: datetime) -> None:
        self.executed.append(run)
        if self._repositories is not None:
            stored = await find_alarm(self._repositories, alarm.id)
            self.stored.append(None if stored is None else stored.occurrence)
        if self._error is not None:
            raise self._error


def make_alarm(
    *,
    recurrence: AlarmRecurrence = DAILY_AT_SIX,
    pre_wake_lead: timedelta | None = timedelta(minutes=30),
    now: datetime = NOW,
    owner_id: str = "owner",
    note: str | None = None,
    name: str | None = None,
) -> Alarm:
    return Alarm.create(
        owner_id=owner_id,
        target=SessionTarget(uuid4()),
        recurrence=recurrence,
        routine=AlarmRoutine(skill="wake-up", note=note),
        now=now,
        pre_wake_lead=pre_wake_lead,
        name=name,
    )


def once_at(wake_at: datetime) -> OnceRecurrence:
    return OnceRecurrence(wake_at=wake_at)


async def save_alarm(repositories: UnitOfWork[AlarmRepository], alarm: Alarm) -> Alarm:
    async with repositories() as repository:
        return await repository.save(alarm)


async def find_alarm(
    repositories: UnitOfWork[AlarmRepository],
    alarm_id: UUID,
) -> Alarm | None:
    async with repositories() as repository:
        return await repository.find_by_id(alarm_id)
