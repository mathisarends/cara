from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.infrastructure.database import ScheduledJobModel
from scheduler import DuplicateJobError, JobDefinition, JobStore


class SQLiteJobStore(JobStore):
    """Store scheduled jobs in the database owned by the gateway process."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def add(self, job: JobDefinition, *, replace_existing: bool) -> None:
        async with self._session_factory() as database:
            if replace_existing:
                statement = (
                    update(ScheduledJobModel)
                    .where(ScheduledJobModel.id == job.id)
                    .values(
                        name=job.name,
                        schedule=job.schedule.model_dump(mode="json"),
                        payload=job.payload,
                        enabled=job.enabled,
                    )
                )
                result = await database.execute(statement)
                if result.rowcount == 0:
                    database.add(_to_orm(job))
            else:
                database.add(_to_orm(job))

            try:
                await database.commit()
            except IntegrityError as error:
                await database.rollback()
                raise DuplicateJobError(f"job already exists: {job.id}") from error

    async def get(self, job_id: UUID) -> JobDefinition | None:
        async with self._session_factory() as database:
            model = await database.get(ScheduledJobModel, job_id)
            return _to_domain(model) if model is not None else None

    async def list(self) -> list[JobDefinition]:
        statement = select(ScheduledJobModel).order_by(ScheduledJobModel.id)
        async with self._session_factory() as database:
            models = (await database.scalars(statement)).all()
            return [_to_domain(model) for model in models]

    async def remove(self, job_id: UUID) -> bool:
        statement = delete(ScheduledJobModel).where(ScheduledJobModel.id == job_id)
        async with self._session_factory() as database:
            result = await database.execute(statement)
            await database.commit()
            return result.rowcount == 1


def _to_orm(job: JobDefinition) -> ScheduledJobModel:
    return ScheduledJobModel(
        id=job.id,
        name=job.name,
        schedule=job.schedule.model_dump(mode="json"),
        payload=job.payload,
        enabled=job.enabled,
    )


def _to_domain(model: ScheduledJobModel) -> JobDefinition:
    return JobDefinition.model_validate(
        {
            "id": model.id,
            "name": model.name,
            "schedule": model.schedule,
            "payload": model.payload,
            "enabled": model.enabled,
        }
    )
