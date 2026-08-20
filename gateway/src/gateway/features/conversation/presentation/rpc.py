from enum import IntEnum, StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter

from gateway.features.conversation.presentation.schemas import (
    SessionResponse,
    SessionSnapshotResponse,
    WireSchema,
)


class RpcMethod(StrEnum):
    SESSION_CREATE = "session.create"
    SESSION_GET = "session.get"
    SESSION_SUBSCRIBE = "session.subscribe"
    SESSION_UNSUBSCRIBE = "session.unsubscribe"
    TURN_START = "turn.start"
    TURN_CANCEL = "turn.cancel"


class RpcNotificationMethod(StrEnum):
    SESSION_EVENT = "session.event"


class RpcErrorCode(IntEnum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    RESOURCE_NOT_FOUND = -32004
    TURN_ALREADY_RUNNING = -32009


class RpcSchema(WireSchema):
    """Base class for every JSON-RPC wire object."""


class SessionParams(RpcSchema):
    session_id: UUID


class CreateSessionParams(RpcSchema):
    metadata: dict[str, object] = Field(default_factory=dict)


class StartTurnParams(SessionParams):
    message: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class RpcRequest(RpcSchema):
    jsonrpc: Literal["2.0"]
    id: str | int | None = None

    @property
    def expects_response(self) -> bool:
        return "id" in self.model_fields_set


class CreateSessionRequest(RpcRequest):
    method: Literal[RpcMethod.SESSION_CREATE]
    params: CreateSessionParams = Field(default_factory=CreateSessionParams)


class GetSessionRequest(RpcRequest):
    method: Literal[RpcMethod.SESSION_GET]
    params: SessionParams


class SubscribeSessionRequest(RpcRequest):
    method: Literal[RpcMethod.SESSION_SUBSCRIBE]
    params: SessionParams


class UnsubscribeSessionRequest(RpcRequest):
    method: Literal[RpcMethod.SESSION_UNSUBSCRIBE]
    params: SessionParams


class StartTurnRequest(RpcRequest):
    method: Literal[RpcMethod.TURN_START]
    params: StartTurnParams


class CancelTurnRequest(RpcRequest):
    method: Literal[RpcMethod.TURN_CANCEL]
    params: SessionParams


type ConversationRequest = Annotated[
    CreateSessionRequest
    | GetSessionRequest
    | SubscribeSessionRequest
    | UnsubscribeSessionRequest
    | StartTurnRequest
    | CancelTurnRequest,
    Field(discriminator="method"),
]

CONVERSATION_REQUEST_ADAPTER: TypeAdapter[ConversationRequest] = TypeAdapter(
    ConversationRequest
)


class SubscriptionResult(RpcSchema):
    subscribed: UUID


class UnsubscriptionResult(RpcSchema):
    unsubscribed: UUID


class TurnCommandResult(RpcSchema):
    session_id: UUID


type RpcResult = (
    SessionResponse
    | SessionSnapshotResponse
    | SubscriptionResult
    | UnsubscriptionResult
    | TurnCommandResult
    | None
)


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
    method: str = RpcNotificationMethod.SESSION_EVENT
    params: Any
