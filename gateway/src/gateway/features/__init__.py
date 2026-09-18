import pyrpckit as rpc
from fastapi_canon import Feature

from . import alarm, automation, conversation, health, llm, voice

FEATURES: tuple[Feature, ...] = (
    health.feature,
    alarm.feature,
    automation.feature,
    llm.feature,
    conversation.feature,
    voice.feature,
)
RPC_CHANNELS: tuple[rpc.RpcChannel, ...] = (
    *conversation.rpc_channels,
    *voice.rpc_channels,
)
__all__ = ["FEATURES", "RPC_CHANNELS"]
