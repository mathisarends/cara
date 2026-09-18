from pyrpckit import RpcService

from gateway.features import RPC_CHANNELS
from gateway.features.conversation.presentation.rpc.events import session_channel
from gateway.features.conversation.presentation.rpc.subscriptions import (
    subscription_channel,
)
from gateway.features.voice.presentation.rpc import voice_channel
from gateway.presentation.authentication import authenticate_rpc_connection

gateway_service = RpcService()
gateway_endpoint = gateway_service.socket(
    "/v1/gateway",
    *RPC_CHANNELS,
    subscription_channel,
    session_channel,
    voice_channel,
    connect=authenticate_rpc_connection,
)
gateway_contract = gateway_service.contract(
    title="Cara Gateway",
    description="Typed JSON-RPC API over the Cara Gateway WebSocket.",
    base_url="ws://127.0.0.1:8000",
)
