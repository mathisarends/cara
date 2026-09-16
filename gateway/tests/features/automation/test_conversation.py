from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from gateway.features.automation.domain import (
    ChannelTarget,
    PromptAction,
)
from gateway.features.automation.infrastructure.conversation import (
    ConversationAutomationActionExecutor,
)
from gateway.features.conversation.application import SessionService, TurnService
from gateway.features.conversation.domain import ChannelRef, Session
from gateway.features.voice.application import VoiceTurnService
from gateway.shared import VoiceDelivery


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


class _VoiceTurns:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.started: list[tuple[str, str, dict[str, object]]] = []

    async def start_proactive_in_room(
        self,
        room: str,
        *,
        text: str,
        metadata: dict[str, object],
    ) -> object | None:
        self.started.append((room, text, metadata))
        return object() if self.available else None


async def test_channel_target_opens_the_current_session_before_running() -> None:
    sessions = _Sessions()
    turns = _Turns()
    executor = ConversationAutomationActionExecutor(
        cast(SessionService, sessions),
        cast(TurnService, turns),
        cast(VoiceTurnService, _VoiceTurns()),
    )
    automation_id = uuid4()
    scheduled_for = datetime(2026, 9, 16, 8, tzinfo=UTC)

    await executor.execute(
        automation_id,
        ChannelTarget("voice"),
        PromptAction("Tell the user to call the dentist at 5 PM"),
        None,
        scheduled_for,
    )

    assert sessions.opened == [ChannelRef("voice")]
    [(session_id, prompt, metadata)] = turns.started
    assert session_id == sessions.session.id
    assert "Tell the user to call the dentist at 5 PM" in prompt
    assert metadata["automation_id"] == str(automation_id)


async def test_voice_delivery_runs_proactively_in_the_configured_room() -> None:
    voice_turns = _VoiceTurns()
    executor = ConversationAutomationActionExecutor(
        cast(SessionService, _Sessions()),
        cast(TurnService, _Turns()),
        cast(VoiceTurnService, voice_turns),
    )
    automation_id = uuid4()
    scheduled_for = datetime(2026, 9, 16, 8, tzinfo=UTC)

    await executor.execute(
        automation_id,
        ChannelTarget("voice"),
        PromptAction("Remind the user to buy a train ticket"),
        VoiceDelivery("bedroom"),
        scheduled_for,
    )

    [(room, prompt, metadata)] = voice_turns.started
    assert room == "bedroom"
    assert "buy a train ticket" in prompt
    assert metadata["automation_id"] == str(automation_id)


async def test_voice_delivery_is_skipped_when_the_room_is_offline() -> None:
    voice_turns = _VoiceTurns(available=False)
    executor = ConversationAutomationActionExecutor(
        cast(SessionService, _Sessions()),
        cast(TurnService, _Turns()),
        cast(VoiceTurnService, voice_turns),
    )

    await executor.execute(
        uuid4(),
        ChannelTarget("voice"),
        PromptAction("This run is intentionally dropped"),
        VoiceDelivery("bedroom"),
        datetime(2026, 9, 16, 8, tzinfo=UTC),
    )

    assert voice_turns.started[0][0] == "bedroom"
