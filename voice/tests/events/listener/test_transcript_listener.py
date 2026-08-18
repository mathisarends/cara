import asyncio

from voice.conversation import AssistantMessage, ConversationHistory, HumanMessage
from voice.events import (
    AssistantTextCompleted,
    UserTranscriptionUpdated,
)
from voice.events.bus import EventBus
from voice.events.listener import TranscriptListener
from voice.stt import TranscriptionKind


def test_listener_delegates_final_transcripts_to_conversation_history() -> None:
    async def run() -> tuple[HumanMessage | AssistantMessage, ...]:
        event_bus = EventBus()
        conversation_history = ConversationHistory()
        TranscriptListener(event_bus, conversation_history)

        await event_bus.dispatch(
            UserTranscriptionUpdated(
                turn_id=1,
                text="Hello",
                is_final=False,
                kind=TranscriptionKind.UPDATE,
            )
        )
        await event_bus.dispatch(
            UserTranscriptionUpdated(
                turn_id=1,
                text="Hello there",
                is_final=True,
                kind=TranscriptionKind.END,
            )
        )
        await event_bus.dispatch(
            AssistantTextCompleted(turn_id=1, text="General Kenobi")
        )

        return conversation_history.turns

    assert asyncio.run(run()) == (
        HumanMessage(turn_id=1, transcript="Hello there"),
        AssistantMessage(turn_id=1, transcript="General Kenobi"),
    )


def test_conversation_history_can_be_updated_without_an_event_bus() -> None:
    conversation_history = ConversationHistory()
    message = HumanMessage(turn_id=1, transcript="Hello")

    conversation_history.add(message)

    assert conversation_history.turns == (message,)
