from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, WebSocket

from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.features.conversation.presentation.socket import JsonRpcConnection

event_router = APIRouter(tags=["conversation"])


@event_router.websocket("/v1/conversation", name="conversation_socket")
@inject
async def conversation_socket(
    websocket: WebSocket,
    service: FromDishka[ConversationService],
    broker: FromDishka[EventBroker],
) -> None:
    await JsonRpcConnection(websocket, service, broker).run()
