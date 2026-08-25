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
            _automation_prompt(envelope.payload.instruction),
            metadata,
        )


def _automation_prompt(instruction: str) -> str:
    return (
        "[Scheduled agent run]\n"
        "The scheduled task is now due. Execute the following instruction now:\n"
        f"<instruction>\n{instruction}\n</instruction>\n"
        "Use the available tools when the instruction requires actions. "
        "Respond to the user when a spoken or written response is part of the task. "
        "Do not schedule another automation unless the instruction explicitly says so."
    )
