from collections.abc import AsyncIterator

from pyrpckit import Inject, RpcModule

from gateway.features.voice.presentation.rpc.mapping import voice_event
from gateway.features.voice.presentation.rpc.models import (
    VoiceEventMessage,
    VoiceNotificationMethod,
)
from gateway.presentation.websocket.subscriptions import EventReceiver

voice_events_module = RpcModule()


@voice_events_module.event(
    VoiceNotificationMethod.VOICE_EVENT,
    payload=VoiceEventMessage,
)
async def voice_events(
    receiver: Inject[EventReceiver],
) -> AsyncIterator[VoiceEventMessage]:
    while True:
        yield voice_event(await receiver.receive_voice())
