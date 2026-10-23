import fastapi_rpckit as rpc
from fastapi_canon import Feature

from . import alarm, automation, conversation, health, llm, voice
from .rooms.feature import feature as rooms_feature

FEATURES: tuple[Feature, ...] = (
    health.feature,
    alarm.feature,
    automation.feature,
    llm.feature,
    conversation.feature,
    rooms_feature,
    voice.feature,
)
RPC_CHANNELS: tuple[rpc.RpcChannel, ...] = (
    *conversation.rpc_channels,
    *voice.rpc_channels,
)
__all__ = ["FEATURES", "RPC_CHANNELS"]
