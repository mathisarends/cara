import random

from voice.events import (
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantToolStarted,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded

_TOOL_CALL_ACK_PHRASES = (
    "On it.",
    "Let me check.",
    "One sec.",
    "Give me a moment.",
    "Sure, checking now.",
)


class ToolAcknowledgementListener:
    """Speaks a brief acknowledgement when a tool call follows silence."""

    def __init__(self, *, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._active_turn_id: int | None = None
        self._has_spoken_text = False
        self._ack_spoken = False
        self._last_ack_phrase: str | None = None

        event_bus.on(AssistantResponseStarted, self._on_response_started)
        event_bus.on(AssistantTextChunk, self._on_text_chunk)
        event_bus.on(AssistantToolStarted, self._on_tool_started)
        event_bus.on(VoiceTurnEnded, self._on_turn_ended)

    async def _on_response_started(self, event: AssistantResponseStarted) -> None:
        self._active_turn_id = event.turn_id
        self._has_spoken_text = False
        self._ack_spoken = False

    async def _on_text_chunk(self, event: AssistantTextChunk) -> None:
        if event.turn_id == self._active_turn_id and event.chunk.strip():
            self._has_spoken_text = True

    async def _on_tool_started(self, event: AssistantToolStarted) -> None:
        if (
            event.turn_id != self._active_turn_id
            or self._has_spoken_text
            or self._ack_spoken
        ):
            return

        self._ack_spoken = True
        await self._event_bus.dispatch(
            AssistantTextChunk(
                turn_id=event.turn_id,
                chunk=self._pick_ack_phrase(),
            )
        )

    async def _on_turn_ended(self, event: VoiceTurnEnded) -> None:
        if event.turn_id == self._active_turn_id:
            self._active_turn_id = None
            self._has_spoken_text = False
            self._ack_spoken = False

    def _pick_ack_phrase(self) -> str:
        choices = [
            phrase
            for phrase in _TOOL_CALL_ACK_PHRASES
            if phrase != self._last_ack_phrase
        ]
        phrase = random.choice(choices)
        self._last_ack_phrase = phrase
        return phrase
