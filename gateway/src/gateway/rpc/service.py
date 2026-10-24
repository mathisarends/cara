from fastapi_rpckit import RpcService, ServerVariable

from gateway.features.conversation.presentation.rpc import turn_channel
from gateway.features.conversation.presentation.rpc.events import session_channel
from gateway.features.conversation.presentation.rpc.subscriptions import (
    subscription_channel,
)
from gateway.features.rooms.presentation.rpc import room_channel
from gateway.features.rooms.presentation.rpc.errors import ROOM_REJECTIONS
from gateway.features.voice.presentation.media import voice_media_stream
from gateway.features.voice.presentation.rpc import voice_channel, voice_turn_channel
from gateway.platform.api import API_PREFIX
from gateway.rpc.context import GatewaySocketSession, RoomSocketSession

gateway_service = RpcService(strict_errors=True)
gateway_endpoint = gateway_service.socket(
    "/gateway",
    channels=(
        turn_channel,
        voice_turn_channel,
        subscription_channel,
        session_channel,
        voice_channel,
    ),
    context=GatewaySocketSession,
)
gateway_media_endpoint = gateway_service.stream(
    "/voice-sessions/{voice_session_id}/media",
    voice_media_stream,
    context=GatewaySocketSession,
)
room_endpoint = gateway_service.socket(
    "/rooms/{room_id}/channel",
    channels=(room_channel,),
    context=RoomSocketSession,
    rejects=ROOM_REJECTIONS,
)
gateway_contract = gateway_service.contract(
    title="Cara Gateway",
    description="Typed JSON-RPC API over the Cara Gateway WebSocket.",
    base_url=f"{{gateway_url}}{API_PREFIX}",
    variables={
        "gateway_url": ServerVariable(
            default="ws://127.0.0.1:8000",
            description="Gateway WebSocket base URL.",
        )
    },
)
