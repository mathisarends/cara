from collections.abc import AsyncGenerator

import httpx
import pytest
from dishka import AsyncContainer, Scope
from dishka.integrations.fastapi import DishkaRoute, FromDishka, setup_dishka
from fastapi import Depends, FastAPI, HTTPException
from fastapi_canon import CanonRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import Message, Receive, Send
from starlette.types import Scope as AsgiScope

from gateway.platform.api import http_request_scope
from gateway.shared import Transaction


@pytest.fixture
async def scope_client(
    database_container: AsyncContainer,
) -> AsyncGenerator[tuple[httpx.AsyncClient, list[str], list[list[str]]]]:
    committed: list[str] = []
    actions_at_response_start: list[list[str]] = []
    router = CanonRouter(route_class=DishkaRoute)

    @router.post("/notes", operation_id="write_scope_note")
    async def write_note(
        session: FromDishka[AsyncSession],
        transaction: FromDishka[Transaction],
        parent_id: int | None = None,
        fail: bool = False,
    ) -> dict[str, bool]:
        statement = text(
            "INSERT INTO scope_notes (text, parent_id) VALUES ('saved', :parent_id)"
        )
        await session.execute(statement, {"parent_id": parent_id})
        transaction.after_commit(lambda: committed.append("committed"))
        if fail:
            raise HTTPException(409, "Rejected after writing")
        return {"accepted": True}

    dependency = Depends(http_request_scope, scope="function")
    app = FastAPI(dependencies=[dependency])
    app.include_router(router)
    setup_dishka(database_container, app)

    async def observed_app(scope: AsgiScope, receive: Receive, send: Send) -> None:
        async def observed_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                actions_at_response_start.append(committed.copy())
            await send(message)

        await app(scope, receive, observed_send)

    transport = httpx.ASGITransport(app=observed_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, committed, actions_at_response_start


async def test_http_commits_before_sending_success(
    scope_client: tuple[httpx.AsyncClient, list[str], list[list[str]]],
    database_container: AsyncContainer,
) -> None:
    client, committed, actions_at_response_start = scope_client

    response = await client.post("/notes")

    assert response.status_code == 200
    assert actions_at_response_start == [["committed"]]
    assert committed == ["committed"]
    async with database_container(scope=Scope.REQUEST) as request_container:
        session = await request_container.get(AsyncSession)
        select_note = text("SELECT text FROM scope_notes")
        assert await session.scalar(select_note) == "saved"


@pytest.mark.parametrize(
    ("parameters", "expected_status"),
    [({"fail": True}, 409), ({"parent_id": 999}, 500)],
    ids=["handler-rejected", "commit-rejected"],
)
async def test_failed_http_work_does_not_commit_or_report_success(
    scope_client: tuple[httpx.AsyncClient, list[str], list[list[str]]],
    database_container: AsyncContainer,
    parameters: dict[str, bool | int],
    expected_status: int,
) -> None:
    client, committed, actions_at_response_start = scope_client

    response = await client.post("/notes", params=parameters)

    assert response.status_code == expected_status
    assert committed == []
    assert actions_at_response_start == [[]]
    async with database_container(scope=Scope.REQUEST) as request_container:
        session = await request_container.get(AsyncSession)
        count_notes = text("SELECT COUNT(*) FROM scope_notes")
        assert await session.scalar(count_notes) == 0
