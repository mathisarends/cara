from collections.abc import Awaitable, Callable

import pyrpckit as rpc

from gateway.features.conversation.presentation.rpc.mapping import session_event
from gateway.features.conversation.presentation.rpc.models import (
    RpcNotificationMethod,
)
from gateway.presentation.websocket.subscriptions import EventReceiver


class EventForwarder:
    def __init__(
        self,
        receiver: EventReceiver,
        send: Callable[[rpc.RpcNotification], Awaitable[None]],
    ) -> None:
        self._receiver = receiver
        self._send = send

    async def run(self) -> None:
        while True:
            event = await self._receiver.receive()
            await self._send(
                rpc.RpcNotification(
                    method=RpcNotificationMethod.SESSION_EVENT,
                    params=session_event(event),
                )
            )
