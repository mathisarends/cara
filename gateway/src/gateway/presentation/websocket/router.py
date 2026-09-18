from fastapi import APIRouter, WebSocket
from pyrpckit.dishka import DishkaResolver
from pyrpckit.fastapi import FastApiSocket

from gateway.presentation.rpc.service import gateway_endpoint
from gateway.presentation.websocket.error_mapping import gateway_error_mapper

gateway_router = APIRouter(tags=["gateway"])


@gateway_router.websocket(gateway_endpoint.path, name="gateway_socket")
async def gateway_socket(websocket: WebSocket) -> None:
    # The app container, not the socket's: the resolver opens the session scope.
    await gateway_endpoint.serve(
        FastApiSocket(websocket),
        resolver=DishkaResolver(websocket.app.state.dishka_container),
        error_mapper=gateway_error_mapper,
    )
