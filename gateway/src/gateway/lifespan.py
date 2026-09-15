import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gateway.features.alarm.application import AlarmService
from gateway.features.automation.application import AutomationService
from gateway.features.conversation.application import AgentRuntime
from gateway.presentation.authentication import GatewayAuthenticator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("%s starting up", app.title)
    container = app.state.dishka_container
    await container.get(GatewayAuthenticator)
    await container.get(AgentRuntime)
    await container.get(AutomationService)
    await container.get(AlarmService)
    try:
        yield
    finally:
        await container.close()
        logger.info("%s shutting down", app.title)
