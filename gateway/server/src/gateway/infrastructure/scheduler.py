import logging

from dishka import Provider, Scope, provide
from pydantic_settings import BaseSettings, SettingsConfigDict

from gateway.features.automation.domain import AutomationEnvelope
from gateway.features.automation.infrastructure import AutomationEnvelopeCodec
from scheduler import ScheduledRun, Scheduler, SqliteJobStore

logger = logging.getLogger(__name__)


class SchedulerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    scheduler_database: str = "./scheduler.sqlite3"


class SchedulerProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> SchedulerSettings:
        return SchedulerSettings()

    @provide
    def scheduler(
        self,
        settings: SchedulerSettings,
    ) -> Scheduler[AutomationEnvelope]:
        store = SqliteJobStore[AutomationEnvelope](
            settings.scheduler_database,
            payload_codec=AutomationEnvelopeCodec(),
        )
        return Scheduler(runner=_log_job_run, store=store)


async def _log_job_run(run: ScheduledRun[AutomationEnvelope]) -> None:
    logger.info("Running scheduled job %s: %s", run.job_id, run.payload)
