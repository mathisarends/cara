from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter

from gateway.presentation.websocket.connection import GatewayConnection

gateway_router = APIRouter(tags=["gateway"])


@gateway_router.websocket("/v1/gateway", name="gateway_socket")
@inject
async def gateway_socket(
    connection: FromDishka[GatewayConnection],
) -> None:
    await connection.run()
