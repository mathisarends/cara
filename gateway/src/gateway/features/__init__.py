import pyrpckit as rpc
from fastapi_canon import Feature

from . import alarm, automation, conversation, health, voice

FEATURES: tuple[Feature, ...] = (
    health.feature,
    alarm.feature,
    automation.feature,
    conversation.feature,
    voice.feature,
)
RPC_MODULES: tuple[rpc.RpcModule, ...] = (conversation.rpc_module, voice.rpc_module)
__all__ = ["FEATURES", "RPC_MODULES"]
