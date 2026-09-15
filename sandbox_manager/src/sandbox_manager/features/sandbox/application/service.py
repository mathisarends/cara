import asyncio
import time
from dataclasses import dataclass

from sandbox_manager.features.sandbox.application.errors import (
    InvalidWorkspaceIdError,
)
from sandbox_manager.features.sandbox.application.models import (
    ExecCommand,
    ExecOutcome,
)
from sandbox_manager.features.sandbox.application.ports import SandboxRuntime
from sandbox_manager.features.sandbox.settings import SandboxSettings


class SandboxService:
    def __init__(
        self,
        runtime: SandboxRuntime,
        settings: SandboxSettings,
    ) -> None:
        self._runtime = runtime
        self._settings = settings
        self._sandboxes: dict[str, _Sandbox] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._reaper: asyncio.Task[None] | None = None
        self._closed = False

    async def start(self) -> None:
        await asyncio.to_thread(self._runtime.remove_owned)
        self._reaper = asyncio.create_task(self._reap_loop(), name="sandbox-reaper")

    async def ensure(self, workspace_id: str) -> str:
        _validate_workspace_id(workspace_id)
        lock = self._locks.setdefault(workspace_id, asyncio.Lock())
        async with lock:
            if sandbox := self._sandboxes.get(workspace_id):
                sandbox.last_activity = time.monotonic()
                return sandbox.sandbox_id
            sandbox_id = await asyncio.to_thread(self._runtime.create, workspace_id)
            self._sandboxes[workspace_id] = _Sandbox(
                sandbox_id=sandbox_id,
                last_activity=time.monotonic(),
            )
            return sandbox_id

    async def execute(self, workspace_id: str, command: ExecCommand) -> ExecOutcome:
        sandbox_id = await self.ensure(workspace_id)
        sandbox = self._sandboxes[workspace_id]
        sandbox.active_operations += 1
        try:
            try:
                async with asyncio.timeout(command.timeout_seconds):
                    outcome = await asyncio.to_thread(
                        self._runtime.execute,
                        sandbox_id,
                        command.argv,
                        cwd=command.cwd,
                        env=command.env,
                        stdin=command.stdin,
                    )
            except TimeoutError:
                await self.stop(workspace_id)
                outcome = ExecOutcome(None, b"", b"command timed out", timed_out=True)
            return _bounded(outcome, self._settings.max_output_bytes)
        finally:
            sandbox.active_operations -= 1
            sandbox.last_activity = time.monotonic()

    async def stop(self, workspace_id: str) -> None:
        lock = self._locks.setdefault(workspace_id, asyncio.Lock())
        async with lock:
            sandbox = self._sandboxes.pop(workspace_id, None)
            if sandbox is not None:
                await asyncio.to_thread(self._runtime.remove, sandbox.sandbox_id)

    async def close(self) -> None:
        self._closed = True
        if self._reaper is not None:
            self._reaper.cancel()
            await asyncio.gather(self._reaper, return_exceptions=True)
        for workspace_id in tuple(self._sandboxes):
            await self.stop(workspace_id)

    async def _reap_loop(self) -> None:
        while not self._closed:
            await asyncio.sleep(self._settings.reap_interval_seconds)
            now = time.monotonic()
            expired = [
                workspace_id
                for workspace_id, sandbox in self._sandboxes.items()
                if sandbox.active_operations == 0
                and now - sandbox.last_activity >= self._settings.idle_ttl_seconds
            ]
            for workspace_id in expired:
                await self.stop(workspace_id)


@dataclass(slots=True)
class _Sandbox:
    sandbox_id: str
    last_activity: float
    active_operations: int = 0


def _validate_workspace_id(workspace_id: str) -> None:
    if not workspace_id or not workspace_id.replace("-", "").replace("_", "").isalnum():
        raise InvalidWorkspaceIdError(workspace_id)


def _bounded(outcome: ExecOutcome, limit: int) -> ExecOutcome:
    stdout = outcome.stdout[:limit]
    remaining = max(0, limit - len(stdout))
    return ExecOutcome(
        outcome.exit_code,
        stdout,
        outcome.stderr[:remaining],
        timed_out=outcome.timed_out,
    )
