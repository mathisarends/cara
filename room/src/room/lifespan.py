import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from room.features.room.application import GatewayLink
from room.features.voice.application import RoomVoiceService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("%s starting up", app.title)
    dependency_container = app.state.dishka_container
    gateway_link = await dependency_container.get(GatewayLink)
    room_voice_service = await dependency_container.get(RoomVoiceService)
    voice_task = asyncio.create_task(
        room_voice_service.run(),
        name="room-voice-service",
    )
    gateway_link_task = asyncio.create_task(
        gateway_link.run(),
        name="room-gateway-link",
    )
    try:
        yield
    finally:
        await room_voice_service.stop()
        voice_task.cancel()
        await asyncio.gather(voice_task, return_exceptions=True)
        gateway_link.stop()
        gateway_link_task.cancel()
        await asyncio.gather(gateway_link_task, return_exceptions=True)
        logger.info("%s shutting down", app.title)
