from enum import StrEnum

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


class _SubscriptionMethod(StrEnum):
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    SUBSCRIBE_CHANNEL = "subscribe_channel"
    UNSUBSCRIBE_CHANNEL = "unsubscribe_channel"


@subscription_channel.server.method(
    _SubscriptionMethod.SUBSCRIBE,
    raises=(ResourceNotFoundError,),
)
async def subscribe_session(
    params: SessionParams,
    handler: Inject[EventStreamRpcMethods],
) -> SubscriptionResult:
    return await handler.subscribe_session(params)


@subscription_channel.server.method(_SubscriptionMethod.UNSUBSCRIBE)
async def unsubscribe_session(
    params: SessionParams,
    handler: Inject[EventStreamRpcMethods],
) -> UnsubscriptionResult:
    return await handler.unsubscribe_session(params)


@subscription_channel.server.method(_SubscriptionMethod.SUBSCRIBE_CHANNEL)
async def subscribe_channel(
    params: ChannelParams,
    handler: Inject[EventStreamRpcMethods],
) -> ChannelSubscriptionResult:
    return handler.subscribe_channel(params)


@subscription_channel.server.method(_SubscriptionMethod.UNSUBSCRIBE_CHANNEL)
async def unsubscribe_channel(
    params: ChannelParams,
    handler: Inject[EventStreamRpcMethods],
) -> ChannelUnsubscriptionResult:
    return handler.unsubscribe_channel(params)
