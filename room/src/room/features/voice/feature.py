from fastapi_canon import Feature

from room.features.voice.infrastructure import VoiceProvider

feature = Feature(
    name="voice",
    providers=(VoiceProvider,),
)
