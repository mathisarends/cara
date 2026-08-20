from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter

from gateway.features.conversation.presentation.socket import JsonRpcConnection

event_router = APIRouter(tags=["conversation"])


@event_router.websocket("/v1/conversation", name="conversation_socket")
@inject
async def conversation_socket(
    connection: FromDishka[JsonRpcConnection],
) -> None:
    await connection.run()
