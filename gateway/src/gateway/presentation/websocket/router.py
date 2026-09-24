import asyncio
from uuid import UUID, uuid4

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response, WebSocket, status
from rpckit.dishka import DishkaResolver
from rpckit.fastapi import FastApiSocket
from rpckit.service import RpcEndpoint, RpcStreamEndpoint

from gateway.features.rooms.application import RoomRegistryService
from gateway.features.rooms.domain import RoomNotFoundError, RoomNotRegisteredError
from gateway.presentation.authentication import GatewayAuthenticator
from gateway.presentation.rpc.service import (
    gateway_endpoint,
    gateway_media_endpoint,
    room_endpoint,
)

gateway_router = APIRouter(tags=["gateway"])


@gateway_router.websocket(gateway_endpoint.path, name="gateway_socket")
@inject
async def gateway_socket(
    websocket: WebSocket,
    authenticator: FromDishka[GatewayAuthenticator],
) -> None:
    if not await _authenticate(websocket, authenticator):
        return
    await _serve(gateway_endpoint, websocket)


@gateway_router.websocket(gateway_media_endpoint.path, name="voice_media_socket")
@inject
async def voice_media_socket(
    websocket: WebSocket,
    authenticator: FromDishka[GatewayAuthenticator],
) -> None:
    if not await _authenticate(websocket, authenticator):
        return
    await _serve(gateway_media_endpoint, websocket)


@gateway_router.websocket(room_endpoint.path, name="room_socket")
@inject
async def room_socket(
    websocket: WebSocket,
    room_id: UUID,
    authenticator: FromDishka[GatewayAuthenticator],
    registry: FromDishka[RoomRegistryService],
) -> None:
    if not await _authenticate(websocket, authenticator):
        return
    connection_id = uuid4()
    try:
        registry.connect(room_id, connection_id)
    except (RoomNotFoundError, RoomNotRegisteredError) as error:
        await websocket.close(code=1008, reason=str(error))
        return
    try:
        await _serve(room_endpoint, websocket)
    finally:
        registry.disconnect(room_id, connection_id)


async def _authenticate(
    websocket: WebSocket,
    authenticator: GatewayAuthenticator,
) -> bool:
    if authenticator.accepts_authorization(websocket.headers.get("authorization", "")):
        return True
    await websocket.send_denial_response(
        Response(
            "Unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            media_type="text/plain",
            headers={"WWW-Authenticate": "Bearer"},
        )
    )
    return False


async def _serve(
    endpoint: RpcEndpoint | RpcStreamEndpoint,
    websocket: WebSocket,
) -> None:
    # The app container, not the socket's: the resolver opens the session scope.
    try:
        await endpoint.serve(
            FastApiSocket(websocket),
            resolver=DishkaResolver(websocket.app.state.dishka_container),
        )
    except asyncio.CancelledError:
        # Starlette cancels normal WebSocket teardown after delivering disconnect.
        return
