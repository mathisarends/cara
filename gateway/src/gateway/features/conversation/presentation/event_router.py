from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, WebSocket

from gateway.features.conversation.application import EventBroker
from gateway.features.conversation.presentation.socket import (
    CommandProcessor,
    serve_socket,
)

event_router = APIRouter(prefix="/v1", tags=["events"])


@event_router.websocket("/ws/{client_id}", name="gateway_event_stream")
@inject
async def gateway_socket(
    websocket: WebSocket,
    client_id: str,
    processor: FromDishka[CommandProcessor],
    broker: FromDishka[EventBroker],
) -> None:
    await serve_socket(websocket, client_id, processor, broker)
