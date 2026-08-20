from scheduler.models import ScheduledJob


class MemoryJobStore[PayloadT]:
    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledJob[PayloadT]] = {}

    async def add(self, job: ScheduledJob[PayloadT]) -> None:
        if job.id in self._jobs:
            raise ValueError(f"Job {job.id!r} already exists")
        self._jobs[job.id] = job

    async def update(self, job: ScheduledJob[PayloadT]) -> None:
        if job.id not in self._jobs:
            raise KeyError(f"Job {job.id!r} does not exist")
        self._jobs[job.id] = job

    async def remove(self, job_id: str) -> bool:
        return self._jobs.pop(job_id, None) is not None

    async def get(self, job_id: str) -> ScheduledJob[PayloadT] | None:
        return self._jobs.get(job_id)

    async def list(self) -> tuple[ScheduledJob[PayloadT], ...]:
        return tuple(self._jobs.values())
