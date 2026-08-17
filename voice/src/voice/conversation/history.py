from agent.events import AssistantInterrupted
from voice.events import (
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantTextCompleted,
    UserTranscriptionUpdated,
)
from voice.events.bus import EventBus

from .models import AssistantMessage, ConversationMessage, HumanMessage


class ConversationHistory:
    """Builds an ordered conversation transcript from voice events."""

    def __init__(self, event_bus: EventBus) -> None:
        self._turns: list[ConversationMessage] = []
        self._assistant_text: dict[int, list[str]] = {}
        self._active_assistant_turn_id: int | None = None

        event_bus.on(UserTranscriptionUpdated, self._on_user_transcription_updated)
        event_bus.on(AssistantResponseStarted, self._on_assistant_response_started)
        event_bus.on(AssistantTextChunk, self._on_assistant_text_chunk)
        event_bus.on(AssistantTextCompleted, self._on_assistant_text_completed)
        event_bus.on(AssistantInterrupted, self._on_assistant_interrupted)

    @property
    def turns(self) -> tuple[ConversationMessage, ...]:
        return tuple(self._turns)

    async def _on_user_transcription_updated(
        self, event: UserTranscriptionUpdated
    ) -> None:
        if not event.is_final:
            return
        self._turns.append(
            HumanMessage(
                turn_id=event.turn_id,
                transcript=event.text,
            )
        )

    async def _on_assistant_response_started(
        self, event: AssistantResponseStarted
    ) -> None:
        self._active_assistant_turn_id = event.turn_id
        self._assistant_text[event.turn_id] = []

    async def _on_assistant_text_chunk(self, event: AssistantTextChunk) -> None:
        self._assistant_text.setdefault(event.turn_id, []).append(event.chunk)

    async def _on_assistant_text_completed(self, event: AssistantTextCompleted) -> None:
        self._complete_assistant_turn(event.turn_id, interrupted=False)

    async def _on_assistant_interrupted(self, _: AssistantInterrupted) -> None:
        turn_id = self._active_assistant_turn_id
        if turn_id is not None:
            self._complete_assistant_turn(turn_id, interrupted=True)

    def _complete_assistant_turn(self, turn_id: int, *, interrupted: bool) -> None:
        transcript = "".join(self._assistant_text.pop(turn_id, []))
        if transcript:
            self._turns.append(
                AssistantMessage(
                    turn_id=turn_id,
                    transcript=transcript,
                    interrupted=interrupted,
                )
            )
        if self._active_assistant_turn_id == turn_id:
            self._active_assistant_turn_id = None
