from fastapi_rpckit import Inject, RpcChannel

from gateway.features.conversation.application import SessionService
from gateway.features.conversation.presentation.rpc.models import (
    ChannelParams,
    ChannelSubscriptionResult,
    ChannelUnsubscriptionResult,
    SessionParams,
    SubscriptionResult,
    UnsubscriptionResult,
)
from gateway.presentation.subscriptions import (
    GatewayClient,
    InMemoryEventStream,
)
from gateway.rpc.errors import RESOURCE_NOT_FOUND

subscription_channel = RpcChannel("subscription")


@subscription_channel.method(
    "subscribe",
    raises=(RESOURCE_NOT_FOUND,),
)
async def subscribe_session(
    params: SessionParams,
    session_service: Inject[SessionService],
    event_stream: Inject[InMemoryEventStream],
    gateway_client: Inject[GatewayClient],
) -> SubscriptionResult:
    await session_service.get(params.session_id)
    event_stream.subscribe(gateway_client.id, params.session_id)
    return SubscriptionResult(subscribed=params.session_id)


@subscription_channel.method("unsubscribe")
async def unsubscribe_session(
    params: SessionParams,
    event_stream: Inject[InMemoryEventStream],
    gateway_client: Inject[GatewayClient],
) -> UnsubscriptionResult:
    event_stream.unsubscribe(gateway_client.id, params.session_id)
    return UnsubscriptionResult(unsubscribed=params.session_id)


@subscription_channel.method("subscribe_channel")
async def subscribe_channel(
    params: ChannelParams,
    event_stream: Inject[InMemoryEventStream],
    gateway_client: Inject[GatewayClient],
) -> ChannelSubscriptionResult:
    event_stream.subscribe_channel(gateway_client.id, params.channel)
    return ChannelSubscriptionResult(subscribed_channel=params.channel)


@subscription_channel.method("unsubscribe_channel")
async def unsubscribe_channel(
    params: ChannelParams,
    event_stream: Inject[InMemoryEventStream],
    gateway_client: Inject[GatewayClient],
) -> ChannelUnsubscriptionResult:
    event_stream.unsubscribe_channel(gateway_client.id, params.channel)
    return ChannelUnsubscriptionResult(unsubscribed_channel=params.channel)
