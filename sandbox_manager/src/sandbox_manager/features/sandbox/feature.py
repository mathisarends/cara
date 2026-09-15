from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi_canon import Feature

from sandbox_manager.features.sandbox.application import SandboxService
from sandbox_manager.features.sandbox.infrastructure import SandboxProvider
from sandbox_manager.features.sandbox.presentation import sandbox_router


@asynccontextmanager
async def _start_sandbox_service(app: FastAPI) -> AsyncIterator[None]:
    # Resolving eagerly removes stale sandboxes and starts the reaper before the
    # first request; closing the container stops the service again.
    await app.state.dishka_container.get(SandboxService)
    yield


feature = Feature(
    name="sandbox",
    routers=[sandbox_router],
    providers=[SandboxProvider],
    lifespan=_start_sandbox_service,
)
