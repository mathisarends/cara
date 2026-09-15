import pyrpckit as rpc
from fastapi_canon import Feature

from . import automation, conversation, health

FEATURES: tuple[Feature, ...] = (
    health.feature,
    automation.feature,
    conversation.feature,
)
RPC_MODULES: tuple[rpc.RpcModule, ...] = (
    automation.rpc_module,
    conversation.rpc_module,
)
__all__ = ["FEATURES", "RPC_MODULES"]
