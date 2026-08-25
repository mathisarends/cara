import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent_plugin_api import AgentRunner
from gateway.features.automation.domain import AutomationEnvelope
from gateway.presentation.websocket.authentication import GatewayAuthenticator
from scheduler import Scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("%s starting up", app.title)
    container = app.state.dishka_container
    await container.get(GatewayAuthenticator)
    await container.get(AgentRunner)
    scheduler = await container.get(Scheduler[AutomationEnvelope])
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        await container.close()
        logger.info("%s shutting down", app.title)
