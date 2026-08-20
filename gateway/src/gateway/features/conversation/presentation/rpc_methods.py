from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.features.conversation.presentation.mapping import session_snapshot
from gateway.features.conversation.presentation.rpc import (
    ConversationRpcMethod,
    CreateSessionParams,
    SessionParams,
    StartTurnParams,
    SubscriptionResult,
    TurnCommandResult,
    UnsubscriptionResult,
)
from gateway.features.conversation.presentation.schemas import (
    SessionResponse,
    SessionSnapshotResponse,
)
from gateway.presentation import rpc
from gateway.presentation.rpc import RpcErrorCode


class ConversationRpcMethods(rpc.RpcHandler):
    def __init__(
        self,
        service: ConversationService,
        broker: EventBroker,
        client_id: str,
    ) -> None:
        self._service = service
        self._broker = broker
        self._client_id = client_id

    @rpc.method(
        ConversationRpcMethod.SESSION_CREATE,
        summary="Create a conversation session.",
        errors=(RpcErrorCode.INVALID_PARAMS, RpcErrorCode.INTERNAL_ERROR),
    )
    async def create_session(self, params: CreateSessionParams) -> SessionResponse:
        session = await self._service.create_session(params.metadata)
        return SessionResponse(
            id=session.id,
            created_at=session.created_at,
            metadata=session.metadata,
        )

    @rpc.method(
        ConversationRpcMethod.SESSION_GET,
        summary="Get a conversation session snapshot.",
        errors=(RpcErrorCode.RESOURCE_NOT_FOUND, RpcErrorCode.INTERNAL_ERROR),
    )
    async def get_session(self, params: SessionParams) -> SessionSnapshotResponse:
        return session_snapshot(await self._service.get_session(params.session_id))

    @rpc.method(
        ConversationRpcMethod.SESSION_SUBSCRIBE,
        summary="Subscribe this connection to a conversation session.",
        errors=(RpcErrorCode.RESOURCE_NOT_FOUND, RpcErrorCode.INTERNAL_ERROR),
    )
    async def subscribe_session(self, params: SessionParams) -> SubscriptionResult:
        await self._service.get_session(params.session_id)
        self._broker.subscribe(self._client_id, params.session_id)
        return SubscriptionResult(subscribed=params.session_id)

    @rpc.method(
        ConversationRpcMethod.SESSION_UNSUBSCRIBE,
        summary="Unsubscribe this connection from a conversation session.",
        errors=(RpcErrorCode.INTERNAL_ERROR,),
    )
    async def unsubscribe_session(self, params: SessionParams) -> UnsubscriptionResult:
        self._broker.unsubscribe(self._client_id, params.session_id)
        return UnsubscriptionResult(unsubscribed=params.session_id)

    @rpc.method(
        ConversationRpcMethod.TURN_START,
        summary="Start an agent turn in a conversation session.",
        errors=(
            RpcErrorCode.INVALID_PARAMS,
            RpcErrorCode.RESOURCE_NOT_FOUND,
            RpcErrorCode.TURN_ALREADY_RUNNING,
            RpcErrorCode.INTERNAL_ERROR,
        ),
    )
    async def start_turn(self, params: StartTurnParams) -> TurnCommandResult:
        await self._service.start_turn(
            params.session_id,
            params.message,
            params.metadata,
        )
        return TurnCommandResult(session_id=params.session_id)

    @rpc.method(
        ConversationRpcMethod.TURN_CANCEL,
        summary="Cancel the active turn in a conversation session.",
        errors=(
            RpcErrorCode.INVALID_PARAMS,
            RpcErrorCode.RESOURCE_NOT_FOUND,
            RpcErrorCode.INTERNAL_ERROR,
        ),
    )
    async def cancel_turn(self, params: SessionParams) -> TurnCommandResult:
        await self._service.cancel_turn(params.session_id)
        return TurnCommandResult(session_id=params.session_id)
