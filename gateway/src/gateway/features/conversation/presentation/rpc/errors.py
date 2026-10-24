from fastapi_rpckit import RpcErrorBinding

from gateway.features.conversation.domain import (
    NoActiveTurnError,
    SessionBusyError,
)

TURN_ALREADY_RUNNING = RpcErrorBinding(
    SessionBusyError,
    code="turn_already_running",
    rpc_code=-32009,
    message=lambda error: f"Turn already running: {error}",
)
NO_ACTIVE_TURN = RpcErrorBinding(
    NoActiveTurnError, code="no_active_turn", rpc_code=-32010, message=str
)
