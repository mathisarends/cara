from dishka.integrations.fastapi import FastapiProvider
from fastapi_canon import Feature

from room.platform import PlatformProvider, RoomConfig


def create_platform_feature(room_config: RoomConfig) -> Feature:
    provider = PlatformProvider(room_config)
    return Feature(
        name="platform",
        providers=(provider, FastapiProvider),
    )
