from enum import StrEnum
from pathlib import Path
from uuid import UUID

from voice.integration import VoiceIntegration, VoiceIntegrationContext

# parents[2]: sound.py -> voice/src/voice(project) -> voice
_DEFAULT_SOUNDS_DIR = Path(__file__).parents[2] / "static" / "sounds"


class Earcon(StrEnum):
    WAKE = "wake"
    LISTENING = "listening"
    SUCCESS = "success"
    ERROR = "error"
    SLEEP = "sleep"


class SoundIntegration(VoiceIntegration):
    """Adds earcons to the agent lifecycle through the integration API."""

    def __init__(self, *, sounds_dir: Path | None = None) -> None:
        self._sounds_dir = sounds_dir or _DEFAULT_SOUNDS_DIR
        self._context: VoiceIntegrationContext | None = None
        self._earcons: dict[Earcon, bytes] = {}

    async def prepare(self, context: VoiceIntegrationContext) -> None:
        self._earcons = {
            earcon: (self._sounds_dir / f"{earcon}.wav").read_bytes()
            for earcon in Earcon
        }
        self._context = context

    async def on_wake_word_detected(
        self, name: str, score: float, sequence: int
    ) -> None:
        await self._play(Earcon.WAKE)

    async def on_assistant_response_started(self, turn_id: UUID) -> None:
        await self._play(Earcon.SUCCESS)

    async def on_user_inactivity_timeout(self, timeout_seconds: float) -> None:
        await self._play(Earcon.SLEEP)

    async def on_channel_stopped(self) -> None:
        await self._play(Earcon.SLEEP)

    async def _play(self, earcon: Earcon) -> None:
        if self._context is None:
            raise RuntimeError("SoundIntegration must be prepared before use.")
        await self._context.audio_player.play(self._earcons[earcon])
