from collections.abc import AsyncIterator

from pyrpckit import Inject, RpcChannel

from gateway.features.voice.presentation.rpc.mapping import voice_event
from gateway.features.voice.presentation.rpc.models import VoiceEventMessage
from gateway.presentation.subscriptions import EventReceiver

voice_channel = RpcChannel("voice")


@voice_channel.server.event("event")
async def voice_events(
    receiver: Inject[EventReceiver],
) -> AsyncIterator[VoiceEventMessage]:
    while True:
        yield voice_event(await receiver.receive_voice())
