from abc import ABC, abstractmethod
from uuid import UUID

from scheduler.models import JobDefinition


class DuplicateJobError(ValueError):
    pass


class JobStore(ABC):
    """Persistence port the Scheduler relies on; adapters own the storage details."""

    @abstractmethod
    async def open(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def add(self, job: JobDefinition, *, replace_existing: bool) -> None:
        """Raise DuplicateJobError if *job.id* exists and replace_existing is False."""

    @abstractmethod
    async def get(self, job_id: UUID) -> JobDefinition | None: ...

    @abstractmethod
    async def list(self) -> list[JobDefinition]: ...

    @abstractmethod
    async def remove(self, job_id: UUID) -> bool: ...
