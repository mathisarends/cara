from pyrpckit import Inject, RpcChannel

from gateway.features.conversation.application import SessionService
from gateway.features.conversation.presentation.rpc.models import (
    ChannelParams,
    ChannelSubscriptionResult,
    ChannelUnsubscriptionResult,
    SessionParams,
    SubscriptionResult,
    UnsubscriptionResult,
)
from gateway.presentation.rpc.errors import ResourceNotFoundError
from gateway.presentation.websocket.subscriptions import (
    GatewayClient,
    InMemoryEventStream,
)

subscription_channel = RpcChannel("subscription")


@subscription_channel.server.method(
    "subscribe",
    raises=(ResourceNotFoundError,),
)
async def subscribe_session(
    params: SessionParams,
    sessions: Inject[SessionService],
    stream: Inject[InMemoryEventStream],
    client: Inject[GatewayClient],
) -> SubscriptionResult:
    await sessions.get(params.session_id)
    stream.subscribe(client.id, params.session_id)
    return SubscriptionResult(subscribed=params.session_id)


@subscription_channel.server.method("unsubscribe")
async def unsubscribe_session(
    params: SessionParams,
    stream: Inject[InMemoryEventStream],
    client: Inject[GatewayClient],
) -> UnsubscriptionResult:
    stream.unsubscribe(client.id, params.session_id)
    return UnsubscriptionResult(unsubscribed=params.session_id)


@subscription_channel.server.method("subscribe_channel")
async def subscribe_channel(
    params: ChannelParams,
    stream: Inject[InMemoryEventStream],
    client: Inject[GatewayClient],
) -> ChannelSubscriptionResult:
    stream.subscribe_channel(client.id, params.channel)
    return ChannelSubscriptionResult(subscribed_channel=params.channel)


@subscription_channel.server.method("unsubscribe_channel")
async def unsubscribe_channel(
    params: ChannelParams,
    stream: Inject[InMemoryEventStream],
    client: Inject[GatewayClient],
) -> ChannelUnsubscriptionResult:
    stream.unsubscribe_channel(client.id, params.channel)
    return ChannelUnsubscriptionResult(unsubscribed_channel=params.channel)
