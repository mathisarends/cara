import asyncio
import os
from collections.abc import Mapping
from typing import Any

from agenttoolkit.builtins import (
    DEFAULT_TIMEOUT,
    CommandResult,
    CommandTimeout,
    DockerSandbox,
)


class ManagedSandbox(DockerSandbox):
    """A sandbox that reopens its container once a command has discarded it.

    A timed-out command leaves its process running inside the container, where
    nothing can reap it, so the base class throws the container away. Reopening
    on demand keeps one timeout from ending the session for every command that
    follows it.
    """

    def __init__(self, image: str, **arguments: Any) -> None:
        super().__init__(image, **arguments)
        self._reopen_lock = asyncio.Lock()

    async def execute(
        self,
        command: str,
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
        stdin: str | bytes | None = None,
        timeout: CommandTimeout = DEFAULT_TIMEOUT,
    ) -> CommandResult:
        await self._ensure_open()
        return await super().execute(
            command,
            cwd=cwd,
            env=env,
            stdin=stdin,
            timeout=timeout,
        )

    async def _ensure_open(self) -> None:
        async with self._reopen_lock:
            if not self.is_open:
                await self.open()
