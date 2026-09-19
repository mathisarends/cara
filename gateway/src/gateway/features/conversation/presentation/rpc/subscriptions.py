from pyrpckit import Inject, RpcChannel

from gateway.features.conversation.presentation.rpc.models import (
    ChannelParams,
    ChannelSubscriptionResult,
    ChannelUnsubscriptionResult,
    SessionParams,
    SubscriptionResult,
    UnsubscriptionResult,
)
from gateway.presentation.rpc.errors import ResourceNotFoundError
from gateway.presentation.websocket.subscriptions import EventStreamRpcMethods

subscription_channel = RpcChannel("subscription")


@subscription_channel.server.method(
    "subscribe",
    raises=(ResourceNotFoundError,),
)
async def subscribe_session(
    params: SessionParams,
    handler: Inject[EventStreamRpcMethods],
) -> SubscriptionResult:
    return await handler.subscribe_session(params)


@subscription_channel.server.method("unsubscribe")
async def unsubscribe_session(
    params: SessionParams,
    handler: Inject[EventStreamRpcMethods],
) -> UnsubscriptionResult:
    return await handler.unsubscribe_session(params)


@subscription_channel.server.method("subscribe_channel")
async def subscribe_channel(
    params: ChannelParams,
    handler: Inject[EventStreamRpcMethods],
) -> ChannelSubscriptionResult:
    return handler.subscribe_channel(params)


@subscription_channel.server.method("unsubscribe_channel")
async def unsubscribe_channel(
    params: ChannelParams,
    handler: Inject[EventStreamRpcMethods],
) -> ChannelUnsubscriptionResult:
    return handler.unsubscribe_channel(params)
