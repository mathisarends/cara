import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from gateway.features.alarm.infrastructure import AlarmRuntime
from gateway.features.automation.infrastructure import AutomationRuntime
from gateway.features.conversation.application import AgentRuntime
from gateway.features.voice.infrastructure.settings import VoiceSettings
from gateway.platform.observability import Telemetry
from gateway.presentation.authentication import GatewayAuthenticator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info("%s starting up", app.title)
    container = app.state.dishka_container
    telemetry: Telemetry = app.state.telemetry
    telemetry.instrument_engine(await container.get(AsyncEngine))
    await container.get(GatewayAuthenticator)
    await container.get(VoiceSettings)
    await container.get(AgentRuntime)
    automation = await container.get(AutomationRuntime)
    alarms = await container.get(AlarmRuntime)
    await automation.start()
    try:
        await alarms.start()
        try:
            yield
        finally:
            await alarms.stop()
    finally:
        await automation.stop()
        await container.close()
        telemetry.shutdown()
        logger.info("%s shutting down", app.title)
