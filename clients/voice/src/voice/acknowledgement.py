import random
from pathlib import Path
from uuid import UUID

from voice.integration import VoiceIntegration, VoiceIntegrationContext

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

# parents[2]: acknowledgement.py -> voice -> src -> voice project
_DEFAULT_ACKNOWLEDGEMENTS_DIR = (
    Path(__file__).parents[2] / "static" / "acknowledgements"
)


class ToolAcknowledgementIntegration(VoiceIntegration):
    """Speaks a brief acknowledgement when a tool call follows silence."""

    def __init__(
        self,
        *,
        acknowledgements_dir: Path | None = None,
    ) -> None:
        self._acknowledgements_dir = (
            acknowledgements_dir or _DEFAULT_ACKNOWLEDGEMENTS_DIR
        )
        self._context: VoiceIntegrationContext | None = None
        self._acknowledgements: dict[str, bytes] = {}
        self._active_turn_id: UUID | None = None
        self._has_spoken_text = False
        self._ack_spoken = False
        self._last_acknowledgement: str | None = None

    async def prepare(self, context: VoiceIntegrationContext) -> None:
        self._acknowledgements = {
            name: (self._acknowledgements_dir / f"{name}.wav").read_bytes()
            for name, _ in TOOL_ACKNOWLEDGEMENTS
        }
        self._context = context

    async def on_assistant_response_started(self, turn_id: UUID) -> None:
        self._active_turn_id = turn_id
        self._has_spoken_text = False
        self._ack_spoken = False

    async def on_assistant_text_started(self, turn_id: UUID) -> None:
        if turn_id == self._active_turn_id:
            self._has_spoken_text = True

    async def on_assistant_tool_started(self, name: str) -> None:
        if self._active_turn_id is None or self._has_spoken_text or self._ack_spoken:
            return

        self._ack_spoken = True
        if self._context is None:
            raise RuntimeError(
                "ToolAcknowledgementIntegration must be prepared before use."
            )
        await self._context.audio_player.play(self._pick_acknowledgement())

    async def on_voice_turn_ended(self, turn_id: UUID) -> None:
        if turn_id == self._active_turn_id:
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
