from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.features.automation.domain import (
    AtSchedule,
    Automation,
    AutomationRepository,
    AutomationSchedule,
    AutomationTarget,
    CronSchedule,
    IntervalSchedule,
    PromptAction,
    ScheduleKind,
    SessionTarget,
    TargetKind,
)
from gateway.features.automation.infrastructure.orm import AutomationModel


class SQLAutomationRepository(AutomationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, id: UUID) -> Automation | None:
        model = await self._session.get(AutomationModel, id)
        return self._to_domain(model) if model is not None else None

    async def save(self, domain: Automation) -> Automation:
        model = self._to_orm(domain)
        merged = await self._session.merge(model)
        await self._session.flush()
        await self._session.refresh(merged)
        return self._to_domain(merged)

    async def find_by_owner(self, owner_id: str) -> tuple[Automation, ...]:
        return await self._find(
            select(AutomationModel).where(AutomationModel.owner_id == owner_id)
        )

    async def find_all(self) -> tuple[Automation, ...]:
        statement = select(AutomationModel)
        return await self._find(statement)

    async def remove(self, domain: Automation) -> None:
        statement = delete(AutomationModel).where(AutomationModel.id == domain.id)
        await self._session.execute(statement)
        await self._session.flush()

    def _to_domain(self, orm: AutomationModel) -> Automation:
        return Automation(
            id=orm.id,
            created_at=_as_utc(orm.created_at),
            owner_id=orm.owner_id,
            target=_target(orm),
            schedule=_schedule(orm),
            action=PromptAction(orm.instruction),
            next_run_at=_as_utc(orm.next_run_at),
            name=orm.name,
        )

    def _to_orm(self, domain: Automation) -> AutomationModel:
        model = AutomationModel(
            id=domain.id,
            created_at=domain.created_at,
            owner_id=domain.owner_id,
            name=domain.name,
            target_kind=domain.target.kind,
            target_session_id=domain.target.session_id,
            schedule_kind=domain.schedule.kind,
            instruction=domain.action.instruction,
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
        models = await self._session.scalars(ordered)
        return tuple(self._to_domain(model) for model in models)


def _target(model: AutomationModel) -> AutomationTarget:
    match model:
        case AutomationModel(
            target_kind=TargetKind.SESSION,
            target_session_id=UUID() as id,
        ):
            return SessionTarget(id)
    raise ValueError(f"Automation {model.id} has an invalid target")


def _schedule(model: AutomationModel) -> AutomationSchedule:
    match model:
        case AutomationModel(
            schedule_kind=ScheduleKind.AT,
            schedule_run_at=datetime() as run_at,
        ):
            return AtSchedule(run_at=_as_utc(run_at))
        case AutomationModel(
            schedule_kind=ScheduleKind.INTERVAL,
            schedule_every_seconds=float() as every_seconds,
            schedule_run_immediately=bool() as run_immediately,
        ):
            return IntervalSchedule(
                every=timedelta(seconds=every_seconds),
                run_immediately=run_immediately,
            )
        case AutomationModel(
            schedule_kind=ScheduleKind.CRON,
            schedule_cron_expression=str() as expression,
            schedule_cron_timezone=str() as timezone,
        ):
            return CronSchedule(expression=expression, timezone=timezone)
    raise ValueError(f"Automation {model.id} has an invalid schedule")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
