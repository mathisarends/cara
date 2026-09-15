from enum import IntEnum

import pyrpckit as rpc


class GatewayErrorCode(IntEnum):
    RESOURCE_NOT_FOUND = -32004
    TURN_ALREADY_RUNNING = -32009
    NO_ACTIVE_TURN = -32010
    VOICE_TURN_ALREADY_ACTIVE = -32011
    MEDIA_NOT_CONNECTED = -32012
    NOT_MEDIA_OWNER = -32013


class ResourceNotFoundError(rpc.RpcError):
    code = GatewayErrorCode.RESOURCE_NOT_FOUND
    message = "Resource not found"


class TurnAlreadyRunningError(rpc.RpcError):
    code = GatewayErrorCode.TURN_ALREADY_RUNNING
    message = "Turn already running"


class NoActiveTurnError(rpc.RpcError):
    code = GatewayErrorCode.NO_ACTIVE_TURN
    message = "No active turn"


class VoiceTurnAlreadyActiveRpcError(rpc.RpcError):
    code = GatewayErrorCode.VOICE_TURN_ALREADY_ACTIVE
    message = "Voice turn already active"


class MediaNotConnectedRpcError(rpc.RpcError):
    code = GatewayErrorCode.MEDIA_NOT_CONNECTED
    message = "Media not connected"


class NotMediaOwnerRpcError(rpc.RpcError):
    code = GatewayErrorCode.NOT_MEDIA_OWNER
    message = "Not media owner"
