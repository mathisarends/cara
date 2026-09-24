import rpckit as rpc


class ResourceNotFoundError(rpc.RpcError):
    rpc_code = -32004


class TurnAlreadyRunningError(rpc.RpcError):
    rpc_code = -32009


class NoActiveTurnError(rpc.RpcError):
    rpc_code = -32010


class VoiceTurnAlreadyActiveRpcError(rpc.RpcError):
    code = "voice_turn_already_active"
    rpc_code = -32011


class MediaNotConnectedRpcError(rpc.RpcError):
    code = "media_not_connected"
    rpc_code = -32012


class NotMediaOwnerRpcError(rpc.RpcError):
    code = "not_media_owner"
    rpc_code = -32013
