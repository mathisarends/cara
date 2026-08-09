from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, WebSocket

from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.features.conversation.presentation.socket import serve_socket

event_router = APIRouter(prefix="/v1", tags=["events"])


@event_router.websocket(
    "/sessions/{session_id}/events",
    name="gateway_event_stream",
)
@inject
async def gateway_socket(
    websocket: WebSocket,
    session_id: UUID,
    conversation_service: FromDishka[ConversationService],
    broker: FromDishka[EventBroker],
) -> None:
    await conversation_service.get_session(session_id)
    await serve_socket(websocket, session_id, broker)
