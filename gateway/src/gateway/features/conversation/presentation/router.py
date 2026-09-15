from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import Depends, status
from fastapi_canon import CanonRouter

from gateway.features.conversation.application import SessionService
from gateway.features.conversation.presentation.errors import (
    CONVERSATION_ERRORS,
    SESSION_NOT_FOUND,
)
from gateway.features.conversation.presentation.mapper import (
    to_channel_ref,
    to_session_response,
    to_session_snapshot_response,
)
from gateway.features.conversation.presentation.schemas import (
    CreateSessionRequest,
    OpenSessionRequest,
    SessionResponse,
    SessionSnapshotResponse,
)
from gateway.presentation.authentication import require_token

conversation_router = CanonRouter(
    prefix="/v1/sessions",
    tags=["sessions"],
    route_class=DishkaRoute,
    error_registry=CONVERSATION_ERRORS,
    dependencies=[Depends(require_token)],
)


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
    session = await sessions.create(channel=to_channel_ref(request.channel))
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
    session = await sessions.open(channel=to_channel_ref(request.channel))
    return to_session_response(session)


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
