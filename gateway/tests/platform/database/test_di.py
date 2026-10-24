import asyncio

import pytest
from dishka import AsyncContainer, Scope
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.shared import Transaction


async def test_success_commits_before_running_after_commit_actions(
    database_container: AsyncContainer,
) -> None:
    actions: list[str] = []
    async with database_container(scope=Scope.REQUEST) as request_container:
        producing_session = await request_container.get(AsyncSession)
        assert await request_container.get(AsyncSession) is producing_session
        transaction = await request_container.get(Transaction)
        insert_note = text("INSERT INTO scope_notes (text) VALUES ('saved')")
        await producing_session.execute(insert_note)
        transaction.after_commit(lambda: actions.append("committed"))
        assert actions == []

    async with database_container(scope=Scope.REQUEST) as request_container:
        reading_session = await request_container.get(AsyncSession)
        assert reading_session is not producing_session
        select_note = text("SELECT text FROM scope_notes")
        saved = await reading_session.scalar(select_note)

    assert saved == "saved"
    assert actions == ["committed"]


@pytest.mark.parametrize("failure_type", [ValueError, asyncio.CancelledError])
async def test_failed_scope_rolls_back_without_after_commit_actions(
    database_container: AsyncContainer,
    failure_type: type[BaseException],
) -> None:
    actions: list[str] = []

    with pytest.raises(failure_type, match="aborted request"):
        async with database_container(scope=Scope.REQUEST) as request_container:
            session = await request_container.get(AsyncSession)
            transaction = await request_container.get(Transaction)
            insert_note = text("INSERT INTO scope_notes (text) VALUES ('discarded')")
            await session.execute(insert_note)
            transaction.after_commit(lambda: actions.append("committed"))
            raise failure_type("aborted request")

    async with database_container(scope=Scope.REQUEST) as request_container:
        reading_session = await request_container.get(AsyncSession)
        count_notes = text("SELECT COUNT(*) FROM scope_notes")
        count = await reading_session.scalar(count_notes)

    assert count == 0
    assert actions == []
