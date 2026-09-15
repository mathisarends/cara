import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Self
from uuid import UUID

from gateway.features.alarm.domain.errors import (
    AlarmNotFoundError,
    AlarmStateError,
    InvalidAlarmError,
)
from gateway.features.alarm.domain.occurrence import (
    AlarmPhase,
    DueRun,
    Occurrence,
    OccurrenceState,
)
from gateway.features.alarm.domain.recurrence import (
    AlarmRecurrence,
    OnceRecurrence,
    WeeklyRecurrence,
)
from gateway.features.alarm.domain.routine import AlarmRoutine
from gateway.features.alarm.domain.target import AlarmTarget

MISSED_GRACE = timedelta(minutes=15)
ACTIVE_TIMEOUT = timedelta(minutes=60)
MAX_SNOOZE = timedelta(minutes=60)
MIN_PRE_WAKE_LEAD = timedelta(minutes=1)
MAX_PRE_WAKE_LEAD = timedelta(minutes=120)


class Alarm:
    def __init__(
        self,
        id: UUID,
        created_at: datetime,
        owner_id: str,
        target: AlarmTarget,
        recurrence: AlarmRecurrence,
        routine: AlarmRoutine,
        pre_wake_lead: timedelta | None = None,
        name: str | None = None,
        enabled: bool = True,
        skipped_dates: frozenset[date] = frozenset(),
        occurrence: Occurrence | None = None,
    ) -> None:
        if not owner_id.strip():
            raise InvalidAlarmError("Alarm owner id must not be empty")
        _require_valid_lead(pre_wake_lead)
        self._id = id
        self._created_at = created_at
        self._owner_id = owner_id
        self._target = target
        self._recurrence = recurrence
        self._routine = routine
        self._pre_wake_lead = pre_wake_lead
        self._name = name
        self._enabled = enabled
        self._skipped_dates = skipped_dates
        self._occurrence = occurrence

    @classmethod
    def create(
        cls,
        *,
        owner_id: str,
        target: AlarmTarget,
        recurrence: AlarmRecurrence,
        routine: AlarmRoutine,
        now: datetime,
        pre_wake_lead: timedelta | None = None,
        name: str | None = None,
    ) -> Self:
        _require_future(recurrence, now)
        alarm = cls(
            id=uuid.uuid4(),
            created_at=now,
            owner_id=owner_id,
            target=target,
            recurrence=recurrence,
            routine=routine,
            pre_wake_lead=pre_wake_lead,
            name=name,
        )
        alarm._schedule_after(now)
        return alarm

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def owner_id(self) -> str:
        return self._owner_id

    @property
    def target(self) -> AlarmTarget:
        return self._target

    @property
    def recurrence(self) -> AlarmRecurrence:
        return self._recurrence

    @property
    def routine(self) -> AlarmRoutine:
        return self._routine

    @property
    def pre_wake_lead(self) -> timedelta | None:
        return self._pre_wake_lead

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def skipped_dates(self) -> frozenset[date]:
        return self._skipped_dates

    @property
    def occurrence(self) -> Occurrence | None:
        return self._occurrence

    @property
    def is_finished(self) -> bool:
        """The only occurrence of a one-time alarm has ended."""
        return (
            self._enabled
            and self._occurrence is None
            and isinstance(self._recurrence, OnceRecurrence)
        )

    @property
    def expires_at(self) -> datetime | None:
        """When the current occurrence ends without being carried out further."""
        match self._occurrence:
            case None:
                return None
            case Occurrence(
                state=OccurrenceState.ACTIVE,
                activated_at=datetime() as activated_at,
            ):
                return activated_at + ACTIVE_TIMEOUT
            case Occurrence(
                state=OccurrenceState.SNOOZED,
                snoozed_until=datetime() as snoozed_until,
            ):
                return snoozed_until + MISSED_GRACE
            case Occurrence(wake_at=wake_at):
                return wake_at + MISSED_GRACE

    def is_owned_by(self, owner_id: str) -> bool:
        return self._owner_id == owner_id

    def require_owner(self, owner_id: str) -> None:
        if not self.is_owned_by(owner_id):
            raise AlarmNotFoundError(self._id)

    def next_due_run(self, now: datetime) -> DueRun | None:
        match self._occurrence:
            case Occurrence(state=OccurrenceState.UPCOMING, wake_at=wake_at) if (
                self._pre_wake_lead is not None
            ):
                # A lead that no longer fits before the wake time starts right away.
                due_at = max(wake_at - self._pre_wake_lead, now)
                return self._due(AlarmPhase.PRE_WAKE, due_at, wake_at)
            case Occurrence(
                state=OccurrenceState.UPCOMING | OccurrenceState.PRE_WAKE,
                wake_at=wake_at,
            ):
                return self._due(AlarmPhase.WAKE, wake_at, wake_at)
            case Occurrence(
                state=OccurrenceState.SNOOZED,
                snoozed_until=datetime() as snoozed_until,
                wake_at=wake_at,
            ):
                return self._due(AlarmPhase.SNOOZE_END, snoozed_until, wake_at)
        return None

    def is_due(self, run: DueRun, now: datetime) -> bool:
        current = self.next_due_run(now)
        if (
            current is None
            or current.alarm_id != run.alarm_id
            or current.phase is not run.phase
            or current.wake_at != run.wake_at
        ):
            return False
        # The pre-wake due time slides with ``now`` once the lead no longer fits.
        return run.phase is AlarmPhase.PRE_WAKE or current.due_at == run.due_at

    def start_run(self, run: DueRun, now: datetime) -> None:
        if not self.is_due(run, now):
            raise AlarmStateError(
                f"Alarm {self._id} is not due for {run.phase} "
                f"at {run.due_at.isoformat()}"
            )
        occurrence = self._require_state(*OccurrenceState)
        match run.phase:
            case AlarmPhase.PRE_WAKE:
                self._occurrence = replace(
                    occurrence,
                    state=OccurrenceState.PRE_WAKE,
                )
            case AlarmPhase.WAKE | AlarmPhase.SNOOZE_END:
                self._occurrence = replace(
                    occurrence,
                    state=OccurrenceState.ACTIVE,
                    snoozed_until=None,
                    activated_at=now,
                )

    def snooze(self, duration: timedelta, now: datetime) -> None:
        if not timedelta(0) < duration <= MAX_SNOOZE:
            raise InvalidAlarmError(
                f"Snooze duration must be greater than zero and at most {MAX_SNOOZE}"
            )
        occurrence = self._require_state(
            OccurrenceState.ACTIVE,
            OccurrenceState.SNOOZED,
        )
        self._occurrence = replace(
            occurrence,
            state=OccurrenceState.SNOOZED,
            snooze_count=occurrence.snooze_count + 1,
            snoozed_until=now + duration,
        )

    def dismiss(self, now: datetime) -> None:
        occurrence = self._require_state(
            OccurrenceState.PRE_WAKE,
            OccurrenceState.ACTIVE,
            OccurrenceState.SNOOZED,
        )
        self._end(occurrence, now)

    def expire(self, now: datetime) -> None:
        occurrence = self._require_state(*OccurrenceState)
        expires_at = self.expires_at
        if expires_at is None or now < expires_at:
            raise AlarmStateError(f"Alarm {self._id} has not expired yet")
        self._end(occurrence, now)

    def skip_next(self) -> None:
        match self._recurrence:
            case OnceRecurrence():
                raise AlarmStateError(
                    f"Alarm {self._id} rings only once; delete it instead of skipping"
                )
            case WeeklyRecurrence() as recurrence:
                occurrence = self._require_state(OccurrenceState.UPCOMING)
                skipped = recurrence.local_date(occurrence.wake_at)
                self._skipped_dates = self._skipped_dates | {skipped}
                self._schedule_after(occurrence.wake_at)

    def set_enabled(self, enabled: bool, now: datetime) -> None:
        if enabled == self._enabled:
            return
        if not enabled:
            self._enabled = False
            self._occurrence = None
            return
        _require_future(self._recurrence, now)
        self._enabled = True
        self._schedule_after(now)

    def update(
        self,
        *,
        recurrence: AlarmRecurrence,
        routine: AlarmRoutine,
        now: datetime,
        pre_wake_lead: timedelta | None = None,
        name: str | None = None,
    ) -> None:
        _require_valid_lead(pre_wake_lead)
        _require_future(recurrence, now)
        self._recurrence = recurrence
        self._routine = routine
        self._pre_wake_lead = pre_wake_lead
        self._name = name
        self._skipped_dates = frozenset()
        self._occurrence = None
        if self._enabled:
            self._schedule_after(now)

    def _due(self, phase: AlarmPhase, due_at: datetime, wake_at: datetime) -> DueRun:
        return DueRun(alarm_id=self._id, phase=phase, due_at=due_at, wake_at=wake_at)

    def _require_state(self, *states: OccurrenceState) -> Occurrence:
        occurrence = self._occurrence
        if occurrence is None:
            raise AlarmStateError(f"Alarm {self._id} has no pending occurrence")
        if occurrence.state not in states:
            raise AlarmStateError(
                f"Alarm {self._id} is {occurrence.state}, "
                f"expected {' or '.join(states)}"
            )
        return occurrence

    def _end(self, occurrence: Occurrence, now: datetime) -> None:
        # Occurrences still inside the grace window remain reachable after an outage.
        self._schedule_after(max(occurrence.wake_at, now - MISSED_GRACE))

    def _schedule_after(self, after: datetime) -> None:
        match self._recurrence:
            case OnceRecurrence(wake_at=wake_at):
                self._occurrence = (
                    Occurrence(wake_at.astimezone(UTC), OccurrenceState.UPCOMING)
                    if wake_at > after
                    else None
                )
            case WeeklyRecurrence() as recurrence:
                earliest = recurrence.local_date(after)
                self._skipped_dates = frozenset(
                    day for day in self._skipped_dates if day >= earliest
                )
                self._occurrence = Occurrence(
                    recurrence.next_wake_at(after, self._skipped_dates),
                    OccurrenceState.UPCOMING,
                )


def _require_valid_lead(lead: timedelta | None) -> None:
    if lead is not None and not MIN_PRE_WAKE_LEAD <= lead <= MAX_PRE_WAKE_LEAD:
        raise InvalidAlarmError(
            f"Pre-wake lead must be between {MIN_PRE_WAKE_LEAD} and {MAX_PRE_WAKE_LEAD}"
        )


def _require_future(recurrence: AlarmRecurrence, now: datetime) -> None:
    match recurrence:
        case OnceRecurrence(wake_at=wake_at) if wake_at <= now:
            raise InvalidAlarmError(
                f"Wake time {wake_at.isoformat()} is not in the future"
            )
