from uuid import UUID

from scheduler.models import JobDefinition
from scheduler.store import DuplicateJobError, JobStore


class InMemoryJobStore(JobStore):
    """Non-persistent adapter for tests, examples, and single-process usage."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, JobDefinition] = {}

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def add(self, job: JobDefinition, *, replace_existing: bool) -> None:
        if not replace_existing and job.id in self._jobs:
            raise DuplicateJobError(f"job already exists: {job.id}")
        self._jobs[job.id] = job

    async def get(self, job_id: UUID) -> JobDefinition | None:
        return self._jobs.get(job_id)

    async def list(self) -> list[JobDefinition]:
        return sorted(self._jobs.values(), key=lambda job: str(job.id))

    async def remove(self, job_id: UUID) -> bool:
        return self._jobs.pop(job_id, None) is not None
