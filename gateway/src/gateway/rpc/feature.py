from fastapi import APIRouter
from fastapi_canon import Feature
from fastapi_rpckit import RpcRoutes
from fastapi_rpckit.integrations.dishka import Dishka

from gateway.rpc.provider import GatewayRpcProvider
from gateway.rpc.service import gateway_endpoint, gateway_media_endpoint, room_endpoint
from gateway.rpc.sessions import (
    ROOM_REJECTIONS,
    RoomDishka,
    open_gateway_session,
    open_room_session,
)

rpc_router = APIRouter(tags=["gateway"])
gateway_resolver = Dishka()
gateway_routes = RpcRoutes(
    rpc_router, context=open_gateway_session, resolver=gateway_resolver
)
gateway_routes.mount(gateway_endpoint)
gateway_routes.mount(gateway_media_endpoint)

room_resolver = RoomDishka()
room_routes = RpcRoutes(
    rpc_router,
    context=open_room_session,
    resolver=room_resolver,
    rejects=ROOM_REJECTIONS,
)
room_routes.mount(room_endpoint)

feature = Feature(name="rpc", routers=[rpc_router], providers=[GatewayRpcProvider])
