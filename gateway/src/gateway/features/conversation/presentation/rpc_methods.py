from typing import assert_never

from agent_protocol.models import Session as ProtocolSession
from agent_protocol.rpc import (
    CancelTurnRequest,
    ConversationRequest,
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
from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.features.conversation.presentation.protocol_mapping import session_snapshot


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

    async def execute(self, request: ConversationRequest) -> RpcResult:
        match request:
            case CreateSessionRequest(params=params):
                session = await self._service.create_session(params.metadata)
                return ProtocolSession(
                    id=session.id,
                    created_at=session.created_at,
                    metadata=session.metadata,
                )
            case GetSessionRequest(params=params):
                return session_snapshot(
                    await self._service.get_session(params.session_id)
                )
            case SubscribeSessionRequest(params=params):
                await self._service.get_session(params.session_id)
                self._broker.subscribe(self._client_id, params.session_id)
                return SubscriptionResult(subscribed=params.session_id)
            case UnsubscribeSessionRequest(params=params):
                self._broker.unsubscribe(self._client_id, params.session_id)
                return UnsubscriptionResult(unsubscribed=params.session_id)
            case StartTurnRequest(params=params):
                await self._service.start_turn(
                    params.session_id, params.message, params.metadata
                )
                return TurnCommandResult(session_id=params.session_id)
            case CancelTurnRequest(params=params):
                await self._service.cancel_turn(params.session_id)
                return TurnCommandResult(session_id=params.session_id)
            case unexpected:
                assert_never(unexpected)
        raise AssertionError("unreachable")
