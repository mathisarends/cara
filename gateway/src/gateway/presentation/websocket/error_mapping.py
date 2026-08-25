from pydantic import ValidationError
from pyrpckit import RpcError, RpcErrorCode

from gateway.features.automation.domain import AutomationNotFoundError
from gateway.features.conversation.domain import SessionBusyError, SessionNotFoundError
from gateway.presentation.rpc import ResourceNotFoundError, TurnAlreadyRunningError


def gateway_error_mapper(error: Exception) -> RpcError | None:
    if isinstance(error, SessionNotFoundError | AutomationNotFoundError):
        return ResourceNotFoundError(f"Not found: {error}")
    if isinstance(error, SessionBusyError):
        return TurnAlreadyRunningError(f"Turn already running: {error}")
    if isinstance(error, ValidationError):
        return None
    if isinstance(error, ValueError):
        return RpcError(f"Invalid params: {error}", code=RpcErrorCode.INVALID_PARAMS)
    return None
