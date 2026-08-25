from gateway.features.conversation.application import ConversationService, EventBroker
from gateway.features.conversation.presentation.rpc import (
    ConversationRpcMethod,
    SessionParams,
    SubscriptionResult,
    UnsubscriptionResult,
)
from gateway.presentation import rpc
from gateway.presentation.rpc import ResourceNotFoundError, RpcInternalError


class SubscriptionRpcMethods(rpc.RpcHandler):
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
        ConversationRpcMethod.SUBSCRIPTION_SUBSCRIBE,
        summary="Subscribe this connection to a conversation session.",
        errors=(ResourceNotFoundError, RpcInternalError),
    )
    async def subscribe_session(self, params: SessionParams) -> SubscriptionResult:
        await self._service.get_session(params.session_id)
        self._broker.subscribe(self._client_id, params.session_id)
        return SubscriptionResult(subscribed=params.session_id)

    @rpc.method(
        ConversationRpcMethod.SUBSCRIPTION_UNSUBSCRIBE,
        summary="Unsubscribe this connection from a conversation session.",
        errors=(RpcInternalError,),
    )
    async def unsubscribe_session(self, params: SessionParams) -> UnsubscriptionResult:
        self._broker.unsubscribe(self._client_id, params.session_id)
        return UnsubscriptionResult(unsubscribed=params.session_id)
