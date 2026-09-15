from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.features.automation.domain import (
    AtSchedule,
    Automation,
    AutomationOrigin,
    AutomationRepository,
    AutomationSchedule,
    AutomationTarget,
    CronSchedule,
    IntervalSchedule,
    PromptAction,
    SessionTarget,
)
from gateway.features.automation.infrastructure.orm import AutomationModel
from gateway.platform.database import Repository


class SQLAutomationRepository(
    Repository[AutomationModel, Automation],
    AutomationRepository,
):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory, AutomationModel)

    async def find_by_owner(self, owner_id: str) -> tuple[Automation, ...]:
        return await self._find(
            select(AutomationModel).where(AutomationModel.owner_id == owner_id)
        )

    async def find_all(self) -> tuple[Automation, ...]:
        return await self._find(select(AutomationModel))

    async def remove(self, domain: Automation) -> None:
        async with self._session_factory() as database:
            await database.execute(
                delete(AutomationModel).where(AutomationModel.id == domain.id)
            )
            await database.commit()

    def _to_domain(self, orm: AutomationModel) -> Automation:
        return Automation(
            id=orm.id,
            created_at=_as_utc(orm.created_at),
            owner_id=orm.owner_id,
            target=_target(orm),
            schedule=_schedule(orm),
            action=PromptAction(orm.instruction),
            origin=AutomationOrigin(orm.created_from_turn_id),
            next_run_at=_as_utc(orm.next_run_at),
            name=orm.name,
        )

    def _to_orm(self, domain: Automation) -> AutomationModel:
        model = AutomationModel(
            id=domain.id,
            created_at=domain.created_at,
            owner_id=domain.owner_id,
            name=domain.name,
            target_kind="session",
            target_session_id=domain.target.session_id,
            schedule_kind=_schedule_kind(domain.schedule),
            instruction=domain.action.instruction,
            created_from_turn_id=domain.origin.created_from_turn_id,
            next_run_at=domain.next_run_at,
        )
        match domain.schedule:
            case AtSchedule(run_at=run_at):
                model.schedule_run_at = run_at
            case IntervalSchedule(every=every, run_immediately=run_immediately):
                model.schedule_every_seconds = every.total_seconds()
                model.schedule_run_immediately = run_immediately
            case CronSchedule(expression=expression, timezone=timezone):
                model.schedule_cron_expression = expression
                model.schedule_cron_timezone = timezone
        return model

    async def _find(
        self,
        statement: Select[tuple[AutomationModel]],
    ) -> tuple[Automation, ...]:
        ordered = statement.order_by(AutomationModel.created_at, AutomationModel.id)
        async with self._session_factory() as database:
            models = await database.scalars(ordered)
            return tuple(self._to_domain(model) for model in models)


def _target(model: AutomationModel) -> AutomationTarget:
    match model:
        case AutomationModel(target_kind="session", target_session_id=UUID() as id):
            return SessionTarget(id)
    raise ValueError(f"Automation {model.id} has an invalid target")


def _schedule_kind(schedule: AutomationSchedule) -> str:
    match schedule:
        case AtSchedule():
            return "at"
        case IntervalSchedule():
            return "interval"
        case CronSchedule():
            return "cron"


def _schedule(model: AutomationModel) -> AutomationSchedule:
    match model:
        case AutomationModel(schedule_kind="at", schedule_run_at=datetime() as run_at):
            return AtSchedule(run_at=_as_utc(run_at))
        case AutomationModel(
            schedule_kind="interval",
            schedule_every_seconds=float() as every_seconds,
            schedule_run_immediately=bool() as run_immediately,
        ):
            return IntervalSchedule(
                every=timedelta(seconds=every_seconds),
                run_immediately=run_immediately,
            )
        case AutomationModel(
            schedule_kind="cron",
            schedule_cron_expression=str() as expression,
            schedule_cron_timezone=str() as timezone,
        ):
            return CronSchedule(expression=expression, timezone=timezone)
    raise ValueError(f"Automation {model.id} has an invalid schedule")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
