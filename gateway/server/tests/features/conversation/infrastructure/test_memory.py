import asyncio
from uuid import uuid4

import pytest

from gateway.features.conversation.domain import GatewayEvent, GatewayEventType
from gateway.features.conversation.infrastructure.memory import InMemoryEventBroker


def _event(session_id) -> GatewayEvent:
    return GatewayEvent(
        type=GatewayEventType.CHAT_DELTA,
        session_id=session_id,
        data={"text": "hi"},
    )


async def _assert_nothing_delivered(receiver) -> None:
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(receiver.receive(), timeout=0.05)


async def test_subscribed_client_receives_published_events() -> None:
    broker = InMemoryEventBroker()
    session_id = uuid4()
    receiver = broker.connect("client-1")
    broker.subscribe("client-1", session_id)
    event = _event(session_id)

    await broker.publish(event)

    assert await receiver.receive() is event


async def test_only_subscribed_clients_receive_events() -> None:
    broker = InMemoryEventBroker()
    session_id = uuid4()
    subscribed = broker.connect("client-1")
    unsubscribed = broker.connect("client-2")
    broker.subscribe("client-1", session_id)

    await broker.publish(_event(session_id))

    await subscribed.receive()
    await _assert_nothing_delivered(unsubscribed)


async def test_events_for_a_different_session_are_not_delivered() -> None:
    broker = InMemoryEventBroker()
    receiver = broker.connect("client-1")
    broker.subscribe("client-1", uuid4())

    await broker.publish(_event(uuid4()))

    await _assert_nothing_delivered(receiver)


async def test_unsubscribing_stops_further_delivery() -> None:
    broker = InMemoryEventBroker()
    session_id = uuid4()
    receiver = broker.connect("client-1")
    broker.subscribe("client-1", session_id)
    broker.unsubscribe("client-1", session_id)

    await broker.publish(_event(session_id))

    await _assert_nothing_delivered(receiver)


async def test_disconnecting_a_client_drops_its_subscriptions_without_error() -> None:
    broker = InMemoryEventBroker()
    session_id = uuid4()
    broker.connect("client-1")
    broker.subscribe("client-1", session_id)

    broker.disconnect("client-1")

    await broker.publish(_event(session_id))


async def test_publishing_an_event_without_a_session_is_a_noop() -> None:
    broker = InMemoryEventBroker()
    receiver = broker.connect("client-1")
    broker.subscribe("client-1", uuid4())

    await broker.publish(_event(session_id=None))

    await _assert_nothing_delivered(receiver)
