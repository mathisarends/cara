from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.features.conversation.domain import (
    Run,
    RunRepository,
    Session,
    SessionRepository,
)
from gateway.infrastructure.database import Repository, RunModel, SessionModel


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SQLSessionRepository(
    Repository[SessionModel, Session],
    SessionRepository,
):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory, SessionModel)

    def _to_domain(self, orm: SessionModel) -> Session:
        return Session(
            id=orm.id,
            created_at=_as_utc(orm.created_at),
            metadata=dict(orm.metadata_json),
        )

    def _to_orm(self, domain: Session) -> SessionModel:
        return SessionModel(
            id=domain.id,
            created_at=domain.created_at,
            metadata_json=dict(domain.metadata),
        )


class SQLRunRepository(Repository[RunModel, Run], RunRepository):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory, RunModel)

    def _to_domain(self, orm: RunModel) -> Run:
        return Run(
            id=orm.id,
            session_id=orm.session_id,
            created_at=_as_utc(orm.created_at),
            status=orm.status,
        )

    def _to_orm(self, domain: Run) -> RunModel:
        return RunModel(
            id=domain.id,
            session_id=domain.session_id,
            created_at=domain.created_at,
            status=domain.status,
        )
