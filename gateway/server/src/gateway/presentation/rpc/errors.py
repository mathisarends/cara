from enum import IntEnum

import pyrpckit as rpc


class GatewayErrorCode(IntEnum):
    RESOURCE_NOT_FOUND = -32004
    TURN_ALREADY_RUNNING = -32009


class ResourceNotFoundError(rpc.RpcError):
    code = GatewayErrorCode.RESOURCE_NOT_FOUND
    message = "Resource not found"


class TurnAlreadyRunningError(rpc.RpcError):
    code = GatewayErrorCode.TURN_ALREADY_RUNNING
    message = "Turn already running"
