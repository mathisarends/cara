from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from gateway.features.automation.domain import ChannelTarget, PromptAction
from gateway.features.automation.infrastructure.conversation import (
    ConversationAutomationActionExecutor,
)
from gateway.features.conversation.application import SessionService, TurnService
from gateway.features.conversation.domain import ChannelRef, Session


class _Sessions:
    def __init__(self) -> None:
        self.opened: list[ChannelRef] = []
        self.session = Session.create(ChannelRef("voice"))

    async def open(self, *, channel: ChannelRef) -> Session:
        self.opened.append(channel)
        return self.session


class _Turns:
    def __init__(self) -> None:
        self.started: list[tuple[UUID, str, dict[str, object]]] = []

    async def start_scheduled(
        self,
        *,
        session_id: UUID,
        text: str,
        metadata: dict[str, object],
    ) -> None:
        self.started.append((session_id, text, metadata))


async def test_channel_target_opens_the_current_session_before_running() -> None:
    sessions = _Sessions()
    turns = _Turns()
    executor = ConversationAutomationActionExecutor(
        cast(SessionService, sessions),
        cast(TurnService, turns),
    )
    automation_id = uuid4()
    scheduled_for = datetime(2026, 9, 16, 8, tzinfo=UTC)

    await executor.execute(
        automation_id,
        ChannelTarget("voice"),
        PromptAction("Tell the user to call the dentist at 5 PM"),
        scheduled_for,
    )

    assert sessions.opened == [ChannelRef("voice")]
    [(session_id, prompt, metadata)] = turns.started
    assert session_id == sessions.session.id
    assert "Tell the user to call the dentist at 5 PM" in prompt
    assert metadata["automation_id"] == str(automation_id)
