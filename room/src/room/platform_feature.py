from dishka.integrations.fastapi import FastapiProvider
from fastapi_canon import Feature

from room.platform import PlatformProvider, RoomConfig
from voice import VoiceSessionConfig


def create_platform_feature(
    room_config: RoomConfig,
    voice_config: VoiceSessionConfig | None,
) -> Feature:
    provider = PlatformProvider(room_config, voice_config)
    return Feature(
        name="platform",
        providers=(provider, FastapiProvider),
    )
