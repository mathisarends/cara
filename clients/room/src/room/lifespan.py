import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from room.features.room.application import GatewayLink

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("%s starting up", app.title)
    dependency_container = app.state.dishka_container
    gateway_link = await dependency_container.get(GatewayLink)
    gateway_link_task = asyncio.create_task(
        gateway_link.run(),
        name="room-gateway-link",
    )
    try:
        yield
    finally:
        gateway_link.stop()
        gateway_link_task.cancel()
        await asyncio.gather(gateway_link_task, return_exceptions=True)
        logger.info("%s shutting down", app.title)
