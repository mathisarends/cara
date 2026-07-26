from typing import Protocol

from cara.tools.sandbox.models import BashSandboxRequest, BashSandboxResult


class BashSandboxError(RuntimeError):
    """Failure to start or control a Bash sandbox."""


class BashSandbox(Protocol):
    async def run(self, request: BashSandboxRequest) -> BashSandboxResult: ...
