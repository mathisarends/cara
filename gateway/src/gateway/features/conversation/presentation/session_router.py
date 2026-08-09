from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter

from gateway.features.conversation.application import ConversationService
from gateway.features.conversation.presentation.schemas import (
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
    service: FromDishka[ConversationService],
) -> SessionResponse:
    session = await service.create_session(request.metadata)
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
    session_id: str,
    service: FromDishka[ConversationService],
) -> SessionResponse:
    session = await service.get_session(session_id)
    return SessionResponse.from_domain(session)
