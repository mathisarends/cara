from rpckit import RpcService, ServerVariable

from gateway.features import RPC_CHANNELS
from gateway.features.conversation.presentation.rpc.events import session_channel
from gateway.features.conversation.presentation.rpc.subscriptions import (
    subscription_channel,
)
from gateway.features.rooms.presentation.rpc import room_channel
from gateway.features.voice.presentation.media import voice_media_stream
from gateway.features.voice.presentation.rpc import voice_channel
from gateway.presentation.error_mapping import gateway_error_mapper

gateway_service = RpcService(error_mapper=gateway_error_mapper)
gateway_endpoint = gateway_service.socket(
    "/v1/gateway",
    channels=(*RPC_CHANNELS, subscription_channel, session_channel, voice_channel),
)
gateway_media_endpoint = gateway_service.stream(
    "/v1/voice-sessions/{voice_session_id}/media",
    voice_media_stream,
)
room_endpoint = gateway_service.socket(
    "/v1/rooms/{room_id}/channel",
    channels=(room_channel,),
)
gateway_contract = gateway_service.contract(
    title="Cara Gateway",
    description="Typed JSON-RPC API over the Cara Gateway WebSocket.",
    base_url="{gateway_url}",
    variables={
        "gateway_url": ServerVariable(
            default="ws://127.0.0.1:8000",
            description="Gateway WebSocket base URL.",
        )
    },
)
