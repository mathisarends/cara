from scheduler import JobDefinition, JobRunner


class GatewayJobRunner(JobRunner):
    """Gateway adapter for scheduled jobs.

    Agent sessions and delivery channels are not part of the gateway composition
    yet. Failing explicitly keeps one-shot jobs persisted for a later retry.
    """

    async def run(self, job: JobDefinition) -> None:
        raise RuntimeError(f"execution is not configured for scheduled job {job.id!r}")
