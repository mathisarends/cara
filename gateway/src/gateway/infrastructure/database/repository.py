from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import SQLModel


class Repository[ORM: SQLModel, Domain](ABC):
    """Generic SQLModel persistence; feature repositories own the mapping."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        model: type[ORM],
    ) -> None:
        self._session_factory = session_factory
        self._model = model

    @abstractmethod
    def _to_domain(self, orm: ORM) -> Domain: ...

    @abstractmethod
    def _to_orm(self, domain: Domain) -> ORM: ...

    async def find_by_id(self, id: str) -> Domain | None:
        async with self._session_factory() as session:
            orm = await session.get(self._model, id)
            return self._to_domain(orm) if orm is not None else None

    async def save(self, domain: Domain) -> Domain:
        async with self._session_factory() as session:
            merged = await session.merge(self._to_orm(domain))
            await session.commit()
            await session.refresh(merged)
            return self._to_domain(merged)
