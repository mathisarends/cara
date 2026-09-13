from pyrpckit import Inject, RpcInternalError, RpcModule

from gateway.features.conversation.presentation.rpc.schemas import (
    ConversationRpcMethod,
    SessionParams,
    SubscriptionResult,
    UnsubscriptionResult,
)
from gateway.presentation.rpc.errors import ResourceNotFoundError
from gateway.presentation.websocket.subscriptions import EventStreamRpcMethods

subscription_module = RpcModule()


@subscription_module.method(
    ConversationRpcMethod.SUBSCRIPTION_SUBSCRIBE,
    errors=(ResourceNotFoundError, RpcInternalError),
)
async def subscribe_session(
    params: SessionParams,
    handler: Inject[EventStreamRpcMethods],
) -> SubscriptionResult:
    return await handler.subscribe_session(params)


@subscription_module.method(
    ConversationRpcMethod.SUBSCRIPTION_UNSUBSCRIBE, errors=(RpcInternalError,)
)
async def unsubscribe_session(
    params: SessionParams,
    handler: Inject[EventStreamRpcMethods],
) -> UnsubscriptionResult:
    return await handler.unsubscribe_session(params)
