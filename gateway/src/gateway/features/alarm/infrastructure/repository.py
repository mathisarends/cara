from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.features.alarm.domain import (
    Alarm,
    AlarmRecurrence,
    AlarmRepository,
    AlarmRoutine,
    AlarmTarget,
    Occurrence,
    OccurrenceState,
    OnceRecurrence,
    RecurrenceKind,
    SessionTarget,
    Weekday,
    WeeklyRecurrence,
)
from gateway.features.alarm.domain.target import TargetKind
from gateway.features.alarm.infrastructure.orm import AlarmModel
from gateway.platform.database import Repository


class SQLAlarmRepository(Repository[AlarmModel, Alarm], AlarmRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory, AlarmModel)

    async def find_by_owner(self, owner_id: str) -> tuple[Alarm, ...]:
        return await self._find(
            select(AlarmModel).where(AlarmModel.owner_id == owner_id)
        )

    async def find_all(self) -> tuple[Alarm, ...]:
        return await self._find(select(AlarmModel))

    async def remove(self, domain: Alarm) -> None:
        async with self._session_factory() as database:
            await database.execute(delete(AlarmModel).where(AlarmModel.id == domain.id))
            await database.commit()

    def _to_domain(self, orm: AlarmModel) -> Alarm:
        return Alarm(
            id=orm.id,
            created_at=_as_utc(orm.created_at),
            owner_id=orm.owner_id,
            target=_target(orm),
            recurrence=_recurrence(orm),
            routine=AlarmRoutine(skill=orm.routine_skill, note=orm.routine_note),
            pre_wake_lead=(
                None
                if orm.pre_wake_lead_seconds is None
                else timedelta(seconds=orm.pre_wake_lead_seconds)
            ),
            name=orm.name,
            enabled=orm.enabled,
            skipped_dates=frozenset(
                date.fromisoformat(day) for day in orm.skipped_dates.split(",") if day
            ),
            occurrence=_occurrence(orm),
        )

    def _to_orm(self, domain: Alarm) -> AlarmModel:
        model = AlarmModel(
            id=domain.id,
            created_at=domain.created_at,
            owner_id=domain.owner_id,
            name=domain.name,
            target_kind=domain.target.kind,
            target_session_id=domain.target.session_id,
            recurrence_kind=domain.recurrence.kind,
            routine_skill=domain.routine.skill,
            routine_note=domain.routine.note,
            pre_wake_lead_seconds=(
                None
                if domain.pre_wake_lead is None
                else int(domain.pre_wake_lead.total_seconds())
            ),
            enabled=domain.enabled,
            skipped_dates=",".join(
                sorted(day.isoformat() for day in domain.skipped_dates)
            ),
        )
        match domain.recurrence:
            case OnceRecurrence(wake_at=wake_at):
                model.once_wake_at = wake_at
            case WeeklyRecurrence(days=days, local_time=local_time, timezone=timezone):
                model.weekly_days = ",".join(day for day in Weekday if day in days)
                model.weekly_local_time = f"{local_time:%H:%M}"
                model.weekly_timezone = timezone
        if (occurrence := domain.occurrence) is not None:
            model.occurrence_wake_at = occurrence.wake_at
            model.occurrence_state = occurrence.state
            model.occurrence_snooze_count = occurrence.snooze_count
            model.occurrence_snoozed_until = occurrence.snoozed_until
            model.occurrence_activated_at = occurrence.activated_at
        return model

    async def _find(self, statement: Select[tuple[AlarmModel]]) -> tuple[Alarm, ...]:
        ordered = statement.order_by(AlarmModel.created_at, AlarmModel.id)
        async with self._session_factory() as database:
            models = await database.scalars(ordered)
            return tuple(self._to_domain(model) for model in models)


def _target(model: AlarmModel) -> AlarmTarget:
    match model:
        case AlarmModel(
            target_kind=TargetKind.SESSION,
            target_session_id=UUID() as id,
        ):
            return SessionTarget(id)
    raise ValueError(f"Alarm {model.id} has an invalid target")


def _recurrence(model: AlarmModel) -> AlarmRecurrence:
    match model:
        case AlarmModel(
            recurrence_kind=RecurrenceKind.ONCE,
            once_wake_at=datetime() as wake_at,
        ):
            return OnceRecurrence(wake_at=_as_utc(wake_at))
        case AlarmModel(
            recurrence_kind=RecurrenceKind.WEEKLY,
            weekly_days=str() as days,
            weekly_local_time=str() as local_time,
            weekly_timezone=str() as timezone,
        ):
            return WeeklyRecurrence(
                days=frozenset(Weekday(day) for day in days.split(",")),
                local_time=time.fromisoformat(local_time),
                timezone=timezone,
            )
    raise ValueError(f"Alarm {model.id} has an invalid recurrence")


def _occurrence(model: AlarmModel) -> Occurrence | None:
    match model:
        case AlarmModel(occurrence_wake_at=None):
            return None
        case AlarmModel(
            occurrence_wake_at=datetime() as wake_at,
            occurrence_state=str() as state,
            occurrence_snooze_count=int() as snooze_count,
        ):
            return Occurrence(
                wake_at=_as_utc(wake_at),
                state=OccurrenceState(state),
                snooze_count=snooze_count,
                snoozed_until=_optional_utc(model.occurrence_snoozed_until),
                activated_at=_optional_utc(model.occurrence_activated_at),
            )
    raise ValueError(f"Alarm {model.id} has an invalid occurrence")


def _optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _as_utc(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
