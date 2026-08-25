from enum import IntEnum

from pyrpckit import RpcError


class GatewayErrorCode(IntEnum):
    RESOURCE_NOT_FOUND = -32004
    TURN_ALREADY_RUNNING = -32009


class ResourceNotFoundError(RpcError):
    code = GatewayErrorCode.RESOURCE_NOT_FOUND
    message = "Resource not found"


class TurnAlreadyRunningError(RpcError):
    code = GatewayErrorCode.TURN_ALREADY_RUNNING
    message = "Turn already running"
