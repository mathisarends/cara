from collections.abc import AsyncIterator

from pyrpckit import Inject, RpcModule

from gateway.features.conversation.presentation.rpc.mapping import session_event
from gateway.features.conversation.presentation.rpc.schemas import (
    RpcNotificationMethod,
    SessionEvent,
)
from gateway.presentation.websocket.subscriptions import EventReceiver

session_events_module = RpcModule()


@session_events_module.event(RpcNotificationMethod.SESSION_EVENT, payload=SessionEvent)
async def session_events(
    receiver: Inject[EventReceiver],
) -> AsyncIterator[SessionEvent]:
    while True:
        yield session_event(await receiver.receive())
