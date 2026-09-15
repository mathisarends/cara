from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from sandbox_manager.features.sandbox.application.models import ExecOutcome


class SandboxRuntime(ABC):
    """Blocking sandbox backend; callers move its calls off the event loop."""

    @abstractmethod
    def create(self, workspace_id: str) -> str:
        """Start a sandbox for the workspace and return its runtime id."""

    @abstractmethod
    def execute(
        self,
        sandbox_id: str,
        argv: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        stdin: bytes | None,
    ) -> ExecOutcome: ...

    @abstractmethod
    def remove(self, sandbox_id: str) -> None: ...

    @abstractmethod
    def remove_owned(self) -> None:
        """Remove every sandbox this manager created, including earlier runs'."""

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def close(self) -> None: ...
