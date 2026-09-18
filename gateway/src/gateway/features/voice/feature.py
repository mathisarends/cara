from fastapi_canon import Feature

from gateway.features.voice.infrastructure import VoiceProvider
from gateway.features.voice.presentation import media_router, voice_router
from gateway.features.voice.presentation.rpc import voice_turn_channel

feature = Feature(
    name="voice",
    routers=(voice_router, media_router),
    providers=(VoiceProvider,),
)
rpc_channels = (voice_turn_channel,)
