import asyncio
from pathlib import Path

from sandbox_manager.features.health.application import (
    DependencyUnavailableError,
    ReadinessCheck,
)
from sandbox_manager.features.sandbox.application import SandboxRuntime


class SandboxRuntimeReadinessCheck(ReadinessCheck):
    def __init__(self, runtime: SandboxRuntime) -> None:
        self._runtime = runtime

    async def check(self) -> None:
        if not await asyncio.to_thread(self._runtime.is_available):
            raise DependencyUnavailableError("sandbox runtime")


class WorkspaceReadinessCheck(ReadinessCheck):
    def __init__(self, root: Path) -> None:
        self._root = root

    async def check(self) -> None:
        if not await asyncio.to_thread(self._root.is_dir):
            raise DependencyUnavailableError("workspace root")
