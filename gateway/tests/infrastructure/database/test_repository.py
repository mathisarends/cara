from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import Field, SQLModel

from gateway.infrastructure.database.repository import Repository


class _NoteModel(SQLModel, table=True):
    __tablename__ = "test_notes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    text: str


@dataclass(frozen=True, slots=True)
class _Note:
    id: UUID
    text: str


class _NoteRepository(Repository[_NoteModel, _Note]):
    def _to_domain(self, orm: _NoteModel) -> _Note:
        return _Note(id=orm.id, text=orm.text)

    def _to_orm(self, domain: _Note) -> _NoteModel:
        return _NoteModel(id=domain.id, text=domain.text)


@pytest.fixture
async def note_repository() -> AsyncIterator[_NoteRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield _NoteRepository(
        async_sessionmaker(engine, expire_on_commit=False), _NoteModel
    )
    await engine.dispose()


async def test_find_by_id_returns_none_when_missing(
    note_repository: _NoteRepository,
) -> None:
    assert await note_repository.find_by_id(uuid4()) is None


async def test_save_persists_and_returns_the_domain_object(
    note_repository: _NoteRepository,
) -> None:
    note = _Note(id=uuid4(), text="hello")

    saved = await note_repository.save(note)

    assert saved == note
    assert await note_repository.find_by_id(note.id) == note


async def test_save_upserts_an_existing_row(note_repository: _NoteRepository) -> None:
    note_id = uuid4()
    await note_repository.save(_Note(id=note_id, text="first"))

    await note_repository.save(_Note(id=note_id, text="second"))

    assert await note_repository.find_by_id(note_id) == _Note(id=note_id, text="second")
