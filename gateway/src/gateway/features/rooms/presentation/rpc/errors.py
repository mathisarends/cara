from fastapi_rpckit import RpcErrorBinding, RpcRejection

from gateway.features.rooms.domain import (
    RoomDeviceNotFoundError,
    RoomNotFoundError,
    RoomNotRegisteredError,
)

ROOM_NOT_FOUND = RpcErrorBinding(
    RoomNotFoundError,
    code="room_not_found",
    message=str,
    rpc_code=-32018,
    rejection=RpcRejection.NOT_FOUND,
)
ROOM_NOT_REGISTERED = RpcErrorBinding(
    RoomNotRegisteredError,
    code="room_not_registered",
    message=str,
    rejection=RpcRejection.FORBIDDEN,
)
ROOM_DEVICE_NOT_FOUND = RpcErrorBinding(
    RoomDeviceNotFoundError,
    code="room_device_not_found",
    message=str,
    rpc_code=-32017,
)
ROOM_REJECTIONS = (ROOM_NOT_FOUND, ROOM_NOT_REGISTERED)
