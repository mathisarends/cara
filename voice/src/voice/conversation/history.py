from agent.events import AssistantInterrupted, ToolCallFinished
from voice.events import (
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantTextCompleted,
    UserTranscriptionUpdated,
)
from voice.events.bus import EventBus

from .models import ConversationRole, ConversationTurn


class ConversationHistory:
    """Builds an ordered conversation transcript from voice events."""

    def __init__(self, event_bus: EventBus) -> None:
        self._turns: list[ConversationTurn] = []
        self._assistant_text: dict[int, list[str]] = {}
        self._assistant_tools: dict[int, list[str]] = {}
        self._active_assistant_turn_id: int | None = None

        event_bus.on(UserTranscriptionUpdated, self._on_user_transcription_updated)
        event_bus.on(AssistantResponseStarted, self._on_assistant_response_started)
        event_bus.on(AssistantTextChunk, self._on_assistant_text_chunk)
        event_bus.on(AssistantTextCompleted, self._on_assistant_text_completed)
        event_bus.on(AssistantInterrupted, self._on_assistant_interrupted)
        event_bus.on(ToolCallFinished, self._on_tool_call_finished)

    @property
    def turns(self) -> tuple[ConversationTurn, ...]:
        return tuple(self._turns)

    async def _on_user_transcription_updated(
        self, event: UserTranscriptionUpdated
    ) -> None:
        if not event.is_final:
            return
        self._turns.append(
            ConversationTurn(
                turn_id=event.turn_id,
                role=ConversationRole.USER,
                transcript=event.text,
            )
        )

    async def _on_assistant_response_started(
        self, event: AssistantResponseStarted
    ) -> None:
        self._active_assistant_turn_id = event.turn_id
        self._assistant_text[event.turn_id] = []
        self._assistant_tools[event.turn_id] = []

    async def _on_assistant_text_chunk(self, event: AssistantTextChunk) -> None:
        self._assistant_text.setdefault(event.turn_id, []).append(event.chunk)

    async def _on_assistant_text_completed(self, event: AssistantTextCompleted) -> None:
        self._complete_assistant_turn(event.turn_id, interrupted=False)

    async def _on_assistant_interrupted(self, _: AssistantInterrupted) -> None:
        turn_id = self._active_assistant_turn_id
        if turn_id is not None:
            self._complete_assistant_turn(turn_id, interrupted=True)

    async def _on_tool_call_finished(self, event: ToolCallFinished) -> None:
        turn_id = self._active_assistant_turn_id
        if turn_id is not None:
            self._assistant_tools.setdefault(turn_id, []).append(event.tool_name)

    def _complete_assistant_turn(self, turn_id: int, *, interrupted: bool) -> None:
        transcript = "".join(self._assistant_text.pop(turn_id, []))
        tools = tuple(self._assistant_tools.pop(turn_id, []))
        if transcript or tools:
            self._turns.append(
                ConversationTurn(
                    turn_id=turn_id,
                    role=ConversationRole.ASSISTANT,
                    transcript=transcript,
                    interrupted=interrupted,
                    tools=tools,
                )
            )
        if self._active_assistant_turn_id == turn_id:
            self._active_assistant_turn_id = None
