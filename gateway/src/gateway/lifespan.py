import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("%s starting up", app.title)
    await app.state.dishka_container.get(AsyncEngine)
    try:
        yield
    finally:
        await app.state.dishka_container.close()
        logger.info("%s shutting down", app.title)
