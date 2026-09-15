import pyrpckit as rpc
from pydantic import ValidationError

from gateway.features.alarm.domain import AlarmNotFoundError, AlarmStateError
from gateway.features.automation.domain import AutomationNotFoundError
from gateway.features.conversation.domain import (
    NoActiveTurnError,
    SessionBusyError,
    SessionNotFoundError,
)
from gateway.presentation.rpc import (
    NoActiveTurnError as NoActiveTurnRpcError,
)
from gateway.presentation.rpc import (
    ResourceNotFoundError,
    TurnAlreadyRunningError,
)


def gateway_error_mapper(error: Exception) -> rpc.RpcError | None:
    if isinstance(
        error,
        SessionNotFoundError | AutomationNotFoundError | AlarmNotFoundError,
    ):
        return ResourceNotFoundError(f"Not found: {error}")
    if isinstance(error, SessionBusyError):
        return TurnAlreadyRunningError(f"Turn already running: {error}")
    if isinstance(error, NoActiveTurnError):
        return NoActiveTurnRpcError(str(error))
    if isinstance(error, ValidationError):
        return None
    # Invalid alarms are ValueErrors and take the branch below.
    if isinstance(error, AlarmStateError | ValueError):
        return rpc.RpcError(
            f"Invalid params: {error}",
            code=rpc.RpcErrorCode.INVALID_PARAMS,
        )
    return None
