import asyncio
import logging
from uuid import uuid4

import pytest

from gateway.features.conversation.application import (
    ConversationEvent,
    ConversationEventType,
)
from gateway.features.conversation.domain import ChannelRef
from gateway.presentation.websocket.subscriptions import InMemoryEventStream


def _event(session_id) -> ConversationEvent:
    return ConversationEvent(
        type=ConversationEventType.CHAT_DELTA,
        session_id=session_id,
        channel=ChannelRef("voice"),
        data={"text": "hi"},
    )


async def _assert_nothing_delivered(receiver) -> None:
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(receiver.receive(), timeout=0.05)


async def test_subscribed_client_receives_published_events() -> None:
    broker = InMemoryEventStream()
    session_id = uuid4()
    receiver = broker.connect("client-1")
    broker.subscribe("client-1", session_id)
    event = _event(session_id)

    await broker.publish(event)

    assert await receiver.receive() is event


async def test_only_subscribed_clients_receive_events() -> None:
    broker = InMemoryEventStream()
    session_id = uuid4()
    subscribed = broker.connect("client-1")
    unsubscribed = broker.connect("client-2")
    broker.subscribe("client-1", session_id)

    await broker.publish(_event(session_id))

    await subscribed.receive()
    await _assert_nothing_delivered(unsubscribed)


async def test_events_for_a_different_session_are_not_delivered() -> None:
    broker = InMemoryEventStream()
    receiver = broker.connect("client-1")
    broker.subscribe("client-1", uuid4())

    await broker.publish(_event(uuid4()))

    await _assert_nothing_delivered(receiver)


async def test_unsubscribing_stops_further_delivery() -> None:
    broker = InMemoryEventStream()
    session_id = uuid4()
    receiver = broker.connect("client-1")
    broker.subscribe("client-1", session_id)
    broker.unsubscribe("client-1", session_id)

    await broker.publish(_event(session_id))

    await _assert_nothing_delivered(receiver)


async def test_disconnecting_a_client_drops_its_subscriptions_without_error() -> None:
    broker = InMemoryEventStream()
    session_id = uuid4()
    broker.connect("client-1")
    broker.subscribe("client-1", session_id)

    broker.disconnect("client-1")

    await broker.publish(_event(session_id))


async def test_lifecycle_events_are_logged_with_delivery_count(caplog) -> None:
    broker = InMemoryEventStream()
    session_id = uuid4()
    broker.connect("client-12345678")
    broker.subscribe("client-12345678", session_id)
    event = ConversationEvent(
        type=ConversationEventType.CHAT_COMPLETED,
        session_id=session_id,
        channel=ChannelRef("voice"),
        sequence=2,
        data={"text": "Assistant reply", "finish_reason": "stop"},
    )

    with caplog.at_level(logging.INFO):
        await broker.publish(event)

    assert (
        f"Emitted event chat.completed for session {session_id} "
        "(sequence=2, recipients=1, text='Assistant reply')"
    ) in caplog.messages


async def test_chat_deltas_are_not_logged_at_info(caplog) -> None:
    broker = InMemoryEventStream()

    with caplog.at_level(logging.INFO):
        await broker.publish(_event(uuid4()))

    assert not any("chat.delta" in message for message in caplog.messages)


async def test_channel_subscriber_receives_events_across_sessions() -> None:
    broker = InMemoryEventStream()
    receiver = broker.connect("voice-client")
    broker.subscribe_channel("voice-client", "voice")
    first = _event(uuid4())
    second = _event(uuid4())

    await broker.publish(first)
    await broker.publish(second)

    assert await receiver.receive() is first
    assert await receiver.receive() is second


async def test_delivery_is_deduplicated_for_session_and_channel_subscriptions() -> None:
    broker = InMemoryEventStream()
    session_id = uuid4()
    receiver = broker.connect("voice-client")
    broker.subscribe("voice-client", session_id)
    broker.subscribe_channel("voice-client", "voice")

    await broker.publish(_event(session_id))

    await receiver.receive()
    await _assert_nothing_delivered(receiver)
