from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import Response, status
from fastapi_canon import CanonResponse, CanonRouter

from gateway.features.conversation.application import SessionService, TurnService
from gateway.features.conversation.presentation.errors import (
    CONVERSATION_ERRORS,
    NO_ACTIVE_TURN,
    SESSION_NOT_FOUND,
    TURN_ALREADY_RUNNING,
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
    StartTurnRequest,
    SteerTurnRequest,
)

conversation_router = CanonRouter(
    prefix="/v1/sessions",
    tags=["sessions"],
    route_class=DishkaRoute,
    error_registry=CONVERSATION_ERRORS,
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


@conversation_router.post(
    "/{session_id}/turn/prepare",
    operation_id="prepare_turn",
    summary="Prepare the agent for an upcoming turn",
    raises=[SESSION_NOT_FOUND],
    response=CanonResponse.empty(description="The agent was prepared."),
)
async def prepare_turn(
    session_id: UUID,
    turns: FromDishka[TurnService],
) -> None:
    await turns.prepare(session_id)


@conversation_router.post(
    "/{session_id}/turn",
    operation_id="start_turn",
    summary="Start a turn",
    raises=[SESSION_NOT_FOUND, TURN_ALREADY_RUNNING],
    response=CanonResponse.empty(
        status=status.HTTP_202_ACCEPTED,
        description="The turn was started; its events stream over the gateway.",
    ),
    response_class=Response,
)
async def start_turn(
    session_id: UUID,
    request: StartTurnRequest,
    turns: FromDishka[TurnService],
) -> None:
    await turns.start(
        session_id=session_id,
        text=request.message,
        metadata=request.metadata,
    )


@conversation_router.post(
    "/{session_id}/turn/steer",
    operation_id="steer_turn",
    summary="Steer the active turn",
    raises=[SESSION_NOT_FOUND, NO_ACTIVE_TURN],
    response=CanonResponse.empty(
        status=status.HTTP_202_ACCEPTED,
        description="The steering message was handed to the active turn.",
    ),
    response_class=Response,
)
async def steer_turn(
    session_id: UUID,
    request: SteerTurnRequest,
    turns: FromDishka[TurnService],
) -> None:
    await turns.steer(session_id=session_id, text=request.message)


@conversation_router.post(
    "/{session_id}/turn/finish",
    operation_id="finish_turn",
    summary="Tell the agent the conversation turn cycle is finished",
    raises=[SESSION_NOT_FOUND],
    response=CanonResponse.empty(description="The agent was finished."),
)
async def finish_turn(
    session_id: UUID,
    turns: FromDishka[TurnService],
) -> None:
    await turns.finish(session_id)


@conversation_router.delete(
    "/{session_id}/turn",
    operation_id="cancel_turn",
    summary="Cancel the active turn",
    raises=[SESSION_NOT_FOUND, NO_ACTIVE_TURN],
    response=CanonResponse.empty(description="The active turn was cancelled."),
)
async def cancel_turn(
    session_id: UUID,
    turns: FromDishka[TurnService],
) -> None:
    await turns.cancel(session_id)
