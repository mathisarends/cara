import logging

from dishka import Provider, Scope, provide
from pydantic_settings import BaseSettings, SettingsConfigDict

from gateway.features.automation.domain import AutomationEnvelope
from gateway.features.automation.infrastructure import AutomationEnvelopeCodec
from gateway.features.conversation.application import ConversationService
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
        conversations: ConversationService,
    ) -> Scheduler[AutomationEnvelope]:
        store = SqliteJobStore[AutomationEnvelope](
            settings.scheduler_database,
            payload_codec=AutomationEnvelopeCodec(),
        )
        return Scheduler(runner=_AutomationRunner(conversations), store=store)


class _AutomationRunner:
    def __init__(self, conversations: ConversationService) -> None:
        self._conversations = conversations

    async def __call__(self, run: ScheduledRun[AutomationEnvelope]) -> None:
        envelope = run.payload
        metadata: dict[str, object] = {
            "origin": "automation",
            "automation_kind": envelope.payload.kind,
            "job_id": run.job_id,
            "scheduled_for": run.scheduled_for.isoformat(),
        }
        logger.info("Running scheduled automation %s", run.job_id)
        await self._conversations.run_automation_turn(
            envelope.target.session_id,
            _reminder_prompt(envelope.payload.message),
            metadata,
        )


def _reminder_prompt(message: str) -> str:
    return (
        "[Scheduled reminder]\n"
        "This reminder is now due. Proactively remind the user about the "
        f"following message: {message}\n"
        "Do not reschedule it unless the user explicitly asks in a later turn."
    )
