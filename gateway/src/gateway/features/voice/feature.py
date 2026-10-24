from fastapi_canon import Feature

from gateway.features.voice.infrastructure import VoiceProvider
from gateway.features.voice.presentation import voice_router

feature = Feature(
    name="voice",
    routers=(voice_router,),
    providers=(VoiceProvider,),
)
