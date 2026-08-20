import logging

from dishka import Provider, Scope, provide
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    def scheduler(self, settings: SchedulerSettings) -> Scheduler[str]:
        store = SqliteJobStore[str](
            settings.scheduler_database,
            payload_codec=_StringCodec(),
        )
        return Scheduler(runner=_log_job_run, store=store)


class _StringCodec:
    def encode(self, value: str) -> str:
        return value

    def decode(self, value: str) -> str:
        return value


async def _log_job_run(run: ScheduledRun[str]) -> None:
    logger.info("Running scheduled job %s: %s", run.job_id, run.payload)
