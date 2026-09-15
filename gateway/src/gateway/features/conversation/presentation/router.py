from datetime import timedelta
from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import Depends, Query, status
from fastapi_canon import CanonRouter

from gateway.features.conversation.application import SessionService
from gateway.features.conversation.presentation.errors import (
    CONVERSATION_ERRORS,
    SESSION_NOT_FOUND,
)
from gateway.features.conversation.presentation.mapper import (
    to_channel_ref,
    to_session_list_response,
    to_session_response,
    to_session_snapshot_response,
    to_sort_order,
)
from gateway.features.conversation.presentation.schemas import (
    CreateSessionRequest,
    OpenSessionRequest,
    SessionListResponse,
    SessionResponse,
    SessionSnapshotResponse,
    SortOrder,
)
from gateway.presentation.authentication import require_token

conversation_router = CanonRouter(
    prefix="/v1/sessions",
    tags=["sessions"],
    route_class=DishkaRoute,
    error_registry=CONVERSATION_ERRORS,
    dependencies=[Depends(require_token)],
)


@conversation_router.get(
    "",
    operation_id="list_sessions",
    response_model=SessionListResponse,
    summary="List sessions ordered by creation time",
)
async def list_sessions(
    sessions: FromDishka[SessionService],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: SortOrder = SortOrder.DESC,
) -> SessionListResponse:
    listed = await sessions.list(limit=limit, order=to_sort_order(sort))
    return to_session_list_response(listed)


@conversation_router.post(
    "",
    operation_id="create_session",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a session",
)
async def create_session(
    request: CreateSessionRequest,
    sessions: FromDishka[SessionService],
) -> SessionResponse:
    inactivity_timeout = _inactivity_timeout(request.inactivity_timeout_seconds)
    session = await sessions.create(
        channel=to_channel_ref(request.channel),
        inactivity_timeout=inactivity_timeout,
    )
    return to_session_response(session)


@conversation_router.post(
    "/open",
    operation_id="open_session",
    response_model=SessionResponse,
    summary="Open the latest session of a channel, creating one if none exists",
)
async def open_session(
    request: OpenSessionRequest,
    sessions: FromDishka[SessionService],
) -> SessionResponse:
    inactivity_timeout = _inactivity_timeout(request.inactivity_timeout_seconds)
    session = await sessions.open(
        channel=to_channel_ref(request.channel),
        inactivity_timeout=inactivity_timeout,
    )
    return to_session_response(session)


def _inactivity_timeout(seconds: float | None) -> timedelta | None:
    return timedelta(seconds=seconds) if seconds is not None else None


@conversation_router.get(
    "/{session_id}",
    operation_id="get_session",
    response_model=SessionSnapshotResponse,
    summary="Get a session snapshot",
    raises=[SESSION_NOT_FOUND],
)
async def get_session(
    session_id: UUID,
    sessions: FromDishka[SessionService],
) -> SessionSnapshotResponse:
    session = await sessions.get(session_id)
    return to_session_snapshot_response(session)
