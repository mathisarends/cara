import pyrpckit as rpc
from fastapi_canon import Feature

from . import alarm, automation, conversation, health

FEATURES: tuple[Feature, ...] = (
    health.feature,
    alarm.feature,
    automation.feature,
    conversation.feature,
)
RPC_MODULES: tuple[rpc.RpcModule, ...] = (
    alarm.rpc_module,
    automation.rpc_module,
    conversation.rpc_module,
)
__all__ = ["FEATURES", "RPC_MODULES"]
