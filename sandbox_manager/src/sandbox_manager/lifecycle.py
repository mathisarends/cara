import asyncio
import time
from dataclasses import dataclass

from sandbox_manager.docker_gateway import DockerGateway, ExecOutcome
from sandbox_manager.models import ExecRequest
from sandbox_manager.settings import SandboxManagerSettings


@dataclass(slots=True)
class _Sandbox:
    container_id: str
    last_activity: float
    active_operations: int = 0


class SandboxManager:
    def __init__(
        self,
        docker: DockerGateway,
        settings: SandboxManagerSettings,
    ) -> None:
        self._docker = docker
        self._settings = settings
        self._sandboxes: dict[str, _Sandbox] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._reaper: asyncio.Task[None] | None = None
        self._closed = False

    async def start(self) -> None:
        await asyncio.to_thread(self._docker.remove_owned)
        self._reaper = asyncio.create_task(self._reap_loop(), name="sandbox-reaper")

    async def ensure(self, workspace_id: str) -> str:
        _validate_workspace_id(workspace_id)
        lock = self._locks.setdefault(workspace_id, asyncio.Lock())
        async with lock:
            if sandbox := self._sandboxes.get(workspace_id):
                sandbox.last_activity = time.monotonic()
                return sandbox.container_id
            container_id = await asyncio.to_thread(self._docker.create, workspace_id)
            self._sandboxes[workspace_id] = _Sandbox(
                container_id=container_id,
                last_activity=time.monotonic(),
            )
            return container_id

    async def execute(self, workspace_id: str, request: ExecRequest) -> ExecOutcome:
        container_id = await self.ensure(workspace_id)
        sandbox = self._sandboxes[workspace_id]
        sandbox.active_operations += 1
        try:
            try:
                async with asyncio.timeout(request.timeout_seconds):
                    outcome = await asyncio.to_thread(
                        self._docker.execute,
                        container_id,
                        request.argv,
                        cwd=request.cwd,
                        env=request.env,
                        stdin=(
                            request.stdin.encode()
                            if request.stdin is not None
                            else None
                        ),
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
                await asyncio.to_thread(self._docker.remove, sandbox.container_id)

    async def close(self) -> None:
        self._closed = True
        if self._reaper is not None:
            self._reaper.cancel()
            await asyncio.gather(self._reaper, return_exceptions=True)
        for workspace_id in tuple(self._sandboxes):
            await self.stop(workspace_id)
        await asyncio.to_thread(self._docker.close)

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


def _validate_workspace_id(workspace_id: str) -> None:
    if not workspace_id or not workspace_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("workspace_id contains unsupported characters")


def _bounded(outcome: ExecOutcome, limit: int) -> ExecOutcome:
    stdout = outcome.stdout[:limit]
    remaining = max(0, limit - len(stdout))
    return ExecOutcome(
        outcome.exit_code,
        stdout,
        outcome.stderr[:remaining],
        timed_out=outcome.timed_out,
    )
