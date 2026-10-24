import logging
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

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
    try:
        engine = await container.get(AsyncEngine)
        telemetry.instrument_engine(engine)
        await container.get(GatewayAuthenticator)
        await container.get(VoiceSettings)
        await container.get(AgentRuntime)
        automation_runtime = await container.get(AutomationRuntime)
        alarm_runtime = await container.get(AlarmRuntime)
        async with AsyncExitStack() as runtimes:
            runtimes.push_async_callback(automation_runtime.stop)
            await automation_runtime.start()
            runtimes.push_async_callback(alarm_runtime.stop)
            await alarm_runtime.start()
            yield
    finally:
        telemetry.shutdown()
        logger.info("%s shutting down", app.title)
