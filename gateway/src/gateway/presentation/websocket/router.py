import asyncio

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response, WebSocket, status
from pyrpckit.dishka import DishkaResolver
from pyrpckit.fastapi import FastApiSocket
from pyrpckit.service import RpcEndpoint, RpcStreamEndpoint

from gateway.presentation.authentication import GatewayAuthenticator
from gateway.presentation.rpc.service import gateway_endpoint, gateway_media_endpoint

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
