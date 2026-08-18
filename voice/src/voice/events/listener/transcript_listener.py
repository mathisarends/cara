from voice.conversation import AssistantMessage, ConversationHistory, HumanMessage
from voice.events import (
    AssistantTextCompleted,
    UserTranscriptionUpdated,
)
from voice.events.bus import EventBus


class TranscriptListener:
    """Translates voice events into conversation history entries."""

    def __init__(
        self, event_bus: EventBus, conversation_history: ConversationHistory
    ) -> None:
        self._conversation_history = conversation_history

        event_bus.on(UserTranscriptionUpdated, self._on_user_transcription_updated)
        event_bus.on(AssistantTextCompleted, self._on_assistant_text_completed)

    async def _on_user_transcription_updated(
        self, event: UserTranscriptionUpdated
    ) -> None:
        if event.is_final:
            self._conversation_history.add(
                HumanMessage(turn_id=event.turn_id, transcript=event.text)
            )

    async def _on_assistant_text_completed(self, event: AssistantTextCompleted) -> None:
        if event.text:
            self._conversation_history.add(
                AssistantMessage(turn_id=event.turn_id, transcript=event.text)
            )
