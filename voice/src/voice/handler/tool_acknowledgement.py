import random
from pathlib import Path

from voice.events import (
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantToolStarted,
    AudioPlaybackRequested,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded

TOOL_ACKNOWLEDGEMENTS = (
    ("on_it", "On it."),
    ("let_me_check", "Let me check."),
    ("one_sec", "One sec."),
    ("give_me_a_moment", "Give me a moment."),
    ("checking_now", "Sure, checking now."),
    ("just_a_moment", "Just a moment."),
    ("take_a_look", "I'll take a look."),
    ("checking_that_now", "Checking that now."),
)

# parents[3]: tool_acknowledgement.py -> handler -> voice -> src -> voice project
_DEFAULT_ACKNOWLEDGEMENTS_DIR = (
    Path(__file__).parents[3] / "static" / "acknowledgements"
)


class ToolAcknowledgementListener:
    """Speaks a brief acknowledgement when a tool call follows silence."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        acknowledgements_dir: Path | None = None,
    ) -> None:
        self._event_bus = event_bus
        directory = acknowledgements_dir or _DEFAULT_ACKNOWLEDGEMENTS_DIR
        self._acknowledgements = {
            name: (directory / f"{name}.wav").read_bytes()
            for name, _ in TOOL_ACKNOWLEDGEMENTS
        }
        self._active_turn_id: int | None = None
        self._has_spoken_text = False
        self._ack_spoken = False
        self._last_acknowledgement: str | None = None

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
        await self._event_bus.request(
            AudioPlaybackRequested(audio=self._pick_acknowledgement())
        )

    async def _on_turn_ended(self, event: VoiceTurnEnded) -> None:
        if event.turn_id == self._active_turn_id:
            self._active_turn_id = None
            self._has_spoken_text = False
            self._ack_spoken = False

    def _pick_acknowledgement(self) -> bytes:
        choices = [
            name
            for name in self._acknowledgements
            if name != self._last_acknowledgement
        ]
        name = random.choice(choices)
        self._last_acknowledgement = name
        return self._acknowledgements[name]
