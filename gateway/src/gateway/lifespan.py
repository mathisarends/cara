import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent_plugin_api import AgentRunner
from gateway.features.automation.application import AutomationService
from gateway.presentation.websocket.authentication import GatewayAuthenticator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("%s starting up", app.title)
    container = app.state.dishka_container
    await container.get(GatewayAuthenticator)
    await container.get(AgentRunner)
    await container.get(AutomationService)
    try:
        yield
    finally:
        await container.close()
        logger.info("%s shutting down", app.title)
