from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RpcErrorCode(IntEnum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    RESOURCE_NOT_FOUND = -32004
    TURN_ALREADY_RUNNING = -32009


class RpcSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RpcErrorData(RpcSchema):
    code: RpcErrorCode
    message: str


class RpcSuccess(RpcSchema):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None
    result: Any


class RpcFailure(RpcSchema):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None
    error: RpcErrorData


class RpcNotification(RpcSchema):
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: Any
