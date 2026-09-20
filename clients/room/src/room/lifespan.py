import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from room.features.room.application import GatewayLink

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("%s starting up", app.title)
    container = app.state.dishka_container
    link = await container.get(GatewayLink)
    link_task = asyncio.create_task(link.run(), name="room-gateway-link")
    try:
        yield
    finally:
        link.stop()
        link_task.cancel()
        await asyncio.gather(link_task, return_exceptions=True)
        logger.info("%s shutting down", app.title)
