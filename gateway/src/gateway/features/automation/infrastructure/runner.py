import logging
from datetime import datetime
from uuid import UUID

from gateway.features.automation.application import (
    AutomationActionExecutor,
    AutomationTargetResolver,
)
from gateway.features.automation.domain import PromptAction, SessionTarget
from gateway.features.automation.infrastructure.codec import AutomationRecord
from gateway.features.conversation.application import SessionService, TurnService
from scheduler import ScheduledRun

logger = logging.getLogger(__name__)


class ConversationAutomationTargetResolver(AutomationTargetResolver):
    def __init__(self, sessions: SessionService) -> None:
        self._sessions = sessions

    async def require_session(self, session_id: UUID) -> None:
        await self._sessions.get(session_id)


class ConversationAutomationActionExecutor(AutomationActionExecutor):
    def __init__(self, turns: TurnService) -> None:
        self._turns = turns

    async def execute(
        self,
        automation_id: str,
        target: SessionTarget,
        action: PromptAction,
        scheduled_for: datetime,
    ) -> None:
        metadata: dict[str, object] = {
            "origin": "automation",
            "automation_kind": "reminder",
            "job_id": automation_id,
            "scheduled_for": scheduled_for.isoformat(),
        }
        logger.info("Running scheduled automation %s", automation_id)
        await self._turns.start_scheduled(
            session_id=target.session_id,
            text=_automation_prompt(action.instruction),
            metadata=metadata,
        )


class SchedulerAutomationRunner:
    def __init__(self, executor: AutomationActionExecutor) -> None:
        self._executor = executor

    async def __call__(self, run: ScheduledRun[AutomationRecord]) -> None:
        await self._executor.execute(
            run.job_id,
            SessionTarget(run.payload.target.session_id),
            PromptAction(run.payload.payload.instruction),
            run.scheduled_for,
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
