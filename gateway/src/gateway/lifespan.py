import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel

from gateway.infrastructure.database import DatabaseSettings, run_migrations

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("%s starting up", app.title)
    settings = await app.state.dishka_container.get(DatabaseSettings)
    if settings.is_in_memory:
        # A fresh in-memory database has no migration history to apply against;
        # create its schema directly instead of running Alembic in a subprocess.
        engine = await app.state.dishka_container.get(AsyncEngine)
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
    else:
        await asyncio.to_thread(run_migrations, settings.async_url)
    try:
        yield
    finally:
        await app.state.dishka_container.close()
        logger.info("%s shutting down", app.title)
