from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.features.conversation.presentation.mapping import session_snapshot
from gateway.features.conversation.presentation.rpc import (
    CancelTurnRequest,
    CreateSessionRequest,
    GetSessionRequest,
    RpcResult,
    StartTurnRequest,
    SubscribeSessionRequest,
    SubscriptionResult,
    TurnCommandResult,
    UnsubscribeSessionRequest,
    UnsubscriptionResult,
)
from gateway.features.conversation.presentation.schemas import SessionResponse
from gateway.presentation.rpc_methods import RpcMethodBinding


class ConversationRpcMethods:
    def __init__(
        self,
        service: ConversationService,
        broker: EventBroker,
        client_id: str,
    ) -> None:
        self._service = service
        self._broker = broker
        self._client_id = client_id

    def bindings(self) -> tuple[RpcMethodBinding, ...]:
        return (
            RpcMethodBinding("session.create", self._create_session),
            RpcMethodBinding("session.get", self._get_session),
            RpcMethodBinding("session.subscribe", self._subscribe_session),
            RpcMethodBinding("session.unsubscribe", self._unsubscribe_session),
            RpcMethodBinding("turn.start", self._start_turn),
            RpcMethodBinding("turn.cancel", self._cancel_turn),
        )

    async def _create_session(self, request: CreateSessionRequest) -> RpcResult:
        session = await self._service.create_session(request.params.metadata)
        return SessionResponse(
            id=session.id,
            created_at=session.created_at,
            metadata=session.metadata,
        )

    async def _get_session(self, request: GetSessionRequest) -> RpcResult:
        return session_snapshot(
            await self._service.get_session(request.params.session_id)
        )

    async def _subscribe_session(self, request: SubscribeSessionRequest) -> RpcResult:
        await self._service.get_session(request.params.session_id)
        self._broker.subscribe(self._client_id, request.params.session_id)
        return SubscriptionResult(subscribed=request.params.session_id)

    async def _unsubscribe_session(
        self, request: UnsubscribeSessionRequest
    ) -> RpcResult:
        self._broker.unsubscribe(self._client_id, request.params.session_id)
        return UnsubscriptionResult(unsubscribed=request.params.session_id)

    async def _start_turn(self, request: StartTurnRequest) -> RpcResult:
        await self._service.start_turn(
            request.params.session_id,
            request.params.message,
            request.params.metadata,
        )
        return TurnCommandResult(session_id=request.params.session_id)

    async def _cancel_turn(self, request: CancelTurnRequest) -> RpcResult:
        await self._service.cancel_turn(request.params.session_id)
        return TurnCommandResult(session_id=request.params.session_id)
