import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gateway.job_runner import GatewayJobRunner
from gateway.settings import GatewaySettings
from scheduler import Scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = GatewaySettings()
    settings.scheduler_database_path.parent.mkdir(parents=True, exist_ok=True)
    scheduler = Scheduler(
        settings.scheduler_database_path,
        GatewayJobRunner(),
        timezone=settings.scheduler_timezone,
    )
    app.state.scheduler = scheduler

    logger.info("%s starting up", app.title)
    async with scheduler:
        logger.info("Scheduler started")
        yield
    logger.info("%s shutting down", app.title)
