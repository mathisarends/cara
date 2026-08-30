from enum import IntEnum

import pyrpckit as rpc


class GatewayErrorCode(IntEnum):
    RESOURCE_NOT_FOUND = -32004
    TURN_ALREADY_RUNNING = -32009
    NO_ACTIVE_TURN = -32010


class ResourceNotFoundError(rpc.RpcError):
    code = GatewayErrorCode.RESOURCE_NOT_FOUND
    message = "Resource not found"


class TurnAlreadyRunningError(rpc.RpcError):
    code = GatewayErrorCode.TURN_ALREADY_RUNNING
    message = "Turn already running"


class NoActiveTurnError(rpc.RpcError):
    code = GatewayErrorCode.NO_ACTIVE_TURN
    message = "No active turn"
