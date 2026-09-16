import asyncio
from uuid import uuid4

import pyrpckit as rpc

from gateway.features.conversation.application import (
    ConversationEvent,
    ConversationEventType,
)
from gateway.features.conversation.domain.values import ChannelRef
from gateway.features.voice.application import VoiceEvent, VoiceEventType
from gateway.presentation.websocket.event_forwarder import EventForwarder
from gateway.presentation.websocket.subscriptions import EventReceiver

_SESSION_ID = uuid4()
_VOICE_SESSION_ID = uuid4()


async def test_both_event_streams_reach_the_client() -> None:
    receiver = EventReceiver()
    sent: list[rpc.RpcNotification] = []

    async def send(notification: rpc.RpcNotification) -> None:
        sent.append(notification)

    forwarder = EventForwarder(receiver, send)
    streams = [
        asyncio.create_task(forwarder.forward_session_events()),
        asyncio.create_task(forwarder.forward_voice_events()),
    ]
    await receiver.put_voice(
        VoiceEvent(
            VoiceEventType.TURN_COMPLETED,
            _VOICE_SESSION_ID,
            _SESSION_ID,
            {},
            voice_turn_id=uuid4(),
            sequence=4,
        )
    )
    await receiver.put(
        ConversationEvent(
            type=ConversationEventType.CHAT_COMPLETED,
            session_id=_SESSION_ID,
            channel=ChannelRef(name="voice"),
            data={"text": "done", "finish_reason": "stop"},
            sequence=1,
        )
    )
    await _settle()
    for stream in streams:
        stream.cancel()
    await asyncio.gather(*streams, return_exceptions=True)

    assert sorted(notification.method for notification in sent) == [
        "session.event",
        "voice.event",
    ]


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)
