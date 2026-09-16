import asyncio
from collections.abc import Awaitable, Callable

import pyrpckit as rpc

from gateway.features.conversation.presentation.rpc.mapping import session_event
from gateway.features.conversation.presentation.rpc.models import (
    RpcNotificationMethod,
)
from gateway.features.voice.presentation.rpc.mapping import voice_event
from gateway.features.voice.presentation.rpc.models import VoiceNotificationMethod
from gateway.presentation.websocket.subscriptions import EventReceiver


class EventForwarder:
    """Sends a client both of its queued event streams as RPC notifications.

    Every notification the channel declares needs a stream here; one that is
    declared but never drained leaves its queue growing while the client waits
    forever for events the Gateway believes it delivered.
    """

    def __init__(
        self,
        receiver: EventReceiver,
        send: Callable[[rpc.RpcNotification], Awaitable[None]],
    ) -> None:
        self._receiver = receiver
        self._send = send

    async def run(self) -> None:
        await asyncio.gather(
            self._forward_session_events(),
            self._forward_voice_events(),
        )

    async def _forward_session_events(self) -> None:
        while True:
            event = await self._receiver.receive()
            await self._send(
                rpc.RpcNotification(
                    method=RpcNotificationMethod.SESSION_EVENT,
                    params=session_event(event),
                )
            )

    async def _forward_voice_events(self) -> None:
        while True:
            event = await self._receiver.receive_voice()
            await self._send(
                rpc.RpcNotification(
                    method=VoiceNotificationMethod.VOICE_EVENT,
                    params=voice_event(event),
                )
            )
