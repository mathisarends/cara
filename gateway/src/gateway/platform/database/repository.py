from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.interfaces import ORMOption
from sqlmodel import SQLModel


class Repository[ORM: SQLModel, Domain](ABC):
    """Generic SQLModel persistence; feature repositories own the mapping."""

    def __init__(self, session: AsyncSession, model: type[ORM]) -> None:
        self._session = session
        self._model = model

    async def find_by_id(self, id: UUID) -> Domain | None:
        orm = await self._session.get(self._model, id, options=self._load_options())
        return self._to_domain(orm) if orm is not None else None

    async def save(self, domain: Domain) -> Domain:
        merged = await self._session.merge(self._to_orm(domain))
        await self._session.flush()
        # Merging leaves the identity map with the caller's state, not the database's.
        reloaded = await self._session.get(
            self._model,
            inspect(merged).identity,
            options=self._load_options(),
            populate_existing=True,
        )
        if reloaded is None:
            raise RuntimeError(f"Saved {self._model.__name__} could not be reloaded")
        return self._to_domain(reloaded)

    @abstractmethod
    def _to_domain(self, orm: ORM) -> Domain: ...

    @abstractmethod
    def _to_orm(self, domain: Domain) -> ORM: ...

    def _load_options(self) -> Sequence[ORMOption]:
        """Eager loads for relationships the mapping reads; async sessions cannot
        lazy load."""
        return ()
