from fastapi import FastAPI
from fastapi_canon import Composition, ErrorOptions

from room.features import FEATURES
from room.lifespan import lifespan
from room.platform import RoomConfig
from room.platform_feature import create_platform_feature
from voice import VoiceSessionConfig


def create_app(
    room_config: RoomConfig,
    voice_config: VoiceSessionConfig | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Cara Room API",
        summary="Local diagnostics for one Cara room process.",
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "system", "description": "Room process availability."},
        ],
    )
    platform_feature = create_platform_feature(room_config, voice_config)
    composition = Composition(
        platform_feature,
        *FEATURES,
        errors=ErrorOptions(type_base="urn:cara:room:problem"),
    )
    composition.apply(app)
    return app
