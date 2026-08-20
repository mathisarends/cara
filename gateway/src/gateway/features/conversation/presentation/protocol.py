from gateway.features.conversation.presentation.events import SessionEvent
from gateway.features.conversation.presentation.rpc import (
    CancelTurnRequest,
    CreateSessionParams,
    CreateSessionRequest,
    GetSessionRequest,
    RpcErrorCode,
    RpcMethod,
    RpcNotificationMethod,
    SessionParams,
    StartTurnParams,
    StartTurnRequest,
    SubscribeSessionRequest,
    SubscriptionResult,
    TurnCommandResult,
    UnsubscribeSessionRequest,
    UnsubscriptionResult,
)
from gateway.features.conversation.presentation.schemas import (
    SessionResponse,
    SessionSnapshotResponse,
)
from gateway.presentation.protocol import (
    RpcFeatureDefinition,
    RpcMethodDefinition,
    RpcNotificationDefinition,
)

CONVERSATION_PROTOCOL = RpcFeatureDefinition(
    name="conversation",
    methods=(
        RpcMethodDefinition(
            name=RpcMethod.SESSION_CREATE,
            request=CreateSessionRequest,
            params=CreateSessionParams,
            result=SessionResponse,
            summary="Create a conversation session.",
            errors=(RpcErrorCode.INVALID_PARAMS, RpcErrorCode.INTERNAL_ERROR),
        ),
        RpcMethodDefinition(
            name=RpcMethod.SESSION_GET,
            request=GetSessionRequest,
            params=SessionParams,
            result=SessionSnapshotResponse,
            summary="Get a conversation session snapshot.",
            errors=(RpcErrorCode.RESOURCE_NOT_FOUND, RpcErrorCode.INTERNAL_ERROR),
        ),
        RpcMethodDefinition(
            name=RpcMethod.SESSION_SUBSCRIBE,
            request=SubscribeSessionRequest,
            params=SessionParams,
            result=SubscriptionResult,
            summary="Subscribe this connection to a conversation session.",
            errors=(RpcErrorCode.RESOURCE_NOT_FOUND, RpcErrorCode.INTERNAL_ERROR),
        ),
        RpcMethodDefinition(
            name=RpcMethod.SESSION_UNSUBSCRIBE,
            request=UnsubscribeSessionRequest,
            params=SessionParams,
            result=UnsubscriptionResult,
            summary="Unsubscribe this connection from a conversation session.",
            errors=(RpcErrorCode.INTERNAL_ERROR,),
        ),
        RpcMethodDefinition(
            name=RpcMethod.TURN_START,
            request=StartTurnRequest,
            params=StartTurnParams,
            result=TurnCommandResult,
            summary="Start an agent turn in a conversation session.",
            errors=(
                RpcErrorCode.INVALID_PARAMS,
                RpcErrorCode.RESOURCE_NOT_FOUND,
                RpcErrorCode.TURN_ALREADY_RUNNING,
                RpcErrorCode.INTERNAL_ERROR,
            ),
        ),
        RpcMethodDefinition(
            name=RpcMethod.TURN_CANCEL,
            request=CancelTurnRequest,
            params=SessionParams,
            result=TurnCommandResult,
            summary="Cancel the active turn in a conversation session.",
            errors=(
                RpcErrorCode.INVALID_PARAMS,
                RpcErrorCode.RESOURCE_NOT_FOUND,
                RpcErrorCode.INTERNAL_ERROR,
            ),
        ),
    ),
    notifications=(
        RpcNotificationDefinition(
            name=RpcNotificationMethod.SESSION_EVENT,
            payload=SessionEvent,
            summary="Publish a subscribed conversation session event.",
        ),
    ),
)
