from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID, uuid4

from dishka.integrations.fastapi import FromDishka
from fastapi import WebSocket
from fastapi_rpckit import RpcReject, RpcRejection
from fastapi_rpckit.dependencies import RpcResolver
from fastapi_rpckit.integrations.dishka import Dishka, DishkaResolver

from gateway.features.rooms.application import RoomRegistryService
from gateway.presentation.authentication import GatewayAuthenticator
from gateway.rpc.context import GatewaySocketSession, RoomSocketSession


async def open_gateway_session(
    websocket: WebSocket,
    gateway_authenticator: FromDishka[GatewayAuthenticator],
) -> GatewaySocketSession:
    _authenticate(websocket, gateway_authenticator)
    return GatewaySocketSession(connection_id=uuid4())


async def open_room_session(
    websocket: WebSocket,
    room_id: UUID,
    gateway_authenticator: FromDishka[GatewayAuthenticator],
    room_registry_service: FromDishka[RoomRegistryService],
) -> RoomSocketSession:
    _authenticate(websocket, gateway_authenticator)
    room_registry_service.require_registered(room_id)
    return RoomSocketSession(connection_id=uuid4(), room_id=room_id)


class RoomConnectionResolver(DishkaResolver):
    @asynccontextmanager
    async def enter_connection(
        self, context: Mapping[type, object]
    ) -> AsyncGenerator[RpcResolver]:
        room_session = cast(RoomSocketSession, context[RoomSocketSession])
        async with super().enter_connection(context) as room_resolver:
            room_registry_service = await room_resolver.resolve(RoomRegistryService)
            room_registry_service.connect(
                room_session.room_id, room_session.connection_id
            )
            try:
                yield room_resolver
            finally:
                room_registry_service.disconnect(
                    room_session.room_id, room_session.connection_id
                )


class RoomDishka(Dishka):
    def for_websocket(self, websocket: WebSocket) -> RoomConnectionResolver:
        return RoomConnectionResolver(websocket.app.state.dishka_container)


def _authenticate(
    websocket: WebSocket, gateway_authenticator: GatewayAuthenticator
) -> None:
    authorization = websocket.headers.get("authorization", "")
    if not gateway_authenticator.accepts_authorization(authorization):
        raise RpcReject(
            RpcRejection.UNAUTHORIZED,
            "Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
