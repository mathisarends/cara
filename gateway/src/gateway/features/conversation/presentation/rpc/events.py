from collections.abc import AsyncIterator

from pyrpckit import Inject, RpcChannel

from gateway.features.conversation.presentation.rpc.mapping import session_event
from gateway.features.conversation.presentation.rpc.models import SessionEvent
from gateway.presentation.subscriptions import EventReceiver

session_channel = RpcChannel("session")


@session_channel.server.event("event")
async def session_events(
    receiver: Inject[EventReceiver],
) -> AsyncIterator[SessionEvent]:
    while True:
        yield session_event(await receiver.receive())
