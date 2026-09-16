import logging
from datetime import datetime
from uuid import UUID

from gateway.features.automation.application import (
    AutomationActionExecutor,
    AutomationTargetResolver,
)
from gateway.features.automation.domain import (
    AutomationTarget,
    ChannelTarget,
    PromptAction,
    SessionTarget,
)
from gateway.features.conversation.application import SessionService, TurnService
from gateway.features.conversation.domain import ChannelRef
from gateway.features.voice.application import VoiceTurnService
from gateway.shared import VoiceDelivery

logger = logging.getLogger(__name__)


class ConversationAutomationTargetResolver(AutomationTargetResolver):
    def __init__(self, sessions: SessionService) -> None:
        self._sessions = sessions

    async def require(self, target: AutomationTarget) -> None:
        match target:
            case SessionTarget(session_id=session_id):
                await self._sessions.get(session_id)
            case ChannelTarget(channel=channel):
                if not channel.strip():
                    raise ValueError("Automation target channel must not be empty")


class ConversationAutomationActionExecutor(AutomationActionExecutor):
    def __init__(
        self,
        sessions: SessionService,
        turns: TurnService,
        voice_turns: VoiceTurnService,
    ) -> None:
        self._sessions = sessions
        self._turns = turns
        self._voice_turns = voice_turns

    async def execute(
        self,
        automation_id: UUID,
        target: AutomationTarget,
        action: PromptAction,
        delivery: VoiceDelivery | None,
        scheduled_for: datetime,
    ) -> None:
        metadata: dict[str, object] = {
            "origin": "automation",
            "automation_kind": "reminder",
            "automation_id": str(automation_id),
            "scheduled_for": scheduled_for.isoformat(),
        }
        logger.info("Running scheduled automation %s", automation_id)
        prompt = _automation_prompt(action.instruction)
        if delivery is not None:
            turn = await self._voice_turns.start_proactive_in_room(
                delivery.room,
                text=prompt,
                metadata=metadata,
            )
            if turn is None:
                logger.warning(
                    "Skipping voice delivery for automation %s because room %r "
                    "is not connected",
                    automation_id,
                    delivery.room,
                )
            return
        match target:
            case SessionTarget(session_id=session_id):
                await self._turns.start_scheduled(
                    session_id=session_id,
                    text=prompt,
                    metadata=metadata,
                )
            case ChannelTarget(channel=channel):
                session = await self._sessions.open(channel=ChannelRef(channel))
                await self._turns.start_scheduled(
                    session_id=session.id,
                    text=prompt,
                    metadata=metadata,
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
