from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Response

from gateway.features.conversation.application import ConversationService
from gateway.features.conversation.presentation.schemas import (
    ChatRequest,
    ErrorResponse,
    SessionCreateRequest,
    SessionResponse,
)

session_router = APIRouter(
    prefix="/v1/sessions",
    tags=["sessions"],
    route_class=DishkaRoute,
)


@session_router.post(
    "",
    operation_id="create_session",
    response_model=SessionResponse,
    response_description="The newly created session.",
    status_code=201,
    summary="Create a session",
)
async def create_session(
    request: SessionCreateRequest,
    conversation_service: FromDishka[ConversationService],
) -> SessionResponse:
    session = await conversation_service.create_session(request.metadata)
    return SessionResponse.from_domain(session)


@session_router.get(
    "/{session_id}",
    operation_id="get_session",
    response_model=SessionResponse,
    response_description="The requested session.",
    responses={404: {"model": ErrorResponse, "description": "Session not found."}},
    summary="Get a session",
)
async def get_session(
    session_id: UUID,
    conversation_service: FromDishka[ConversationService],
) -> SessionResponse:
    session = await conversation_service.get_session(session_id)
    return SessionResponse.from_domain(session)


@session_router.post(
    "/{session_id}/chat",
    operation_id="start_chat",
    response_class=Response,
    status_code=202,
    summary="Start a chat turn",
)
async def start_chat(
    session_id: UUID,
    request: ChatRequest,
    conversation_service: FromDishka[ConversationService],
) -> Response:
    await conversation_service.start_turn(
        session_id,
        request.text,
        request.metadata,
    )
    return Response(status_code=202)
