from enum import StrEnum
from pathlib import Path

from voice.observer import Observer, ObserverContext

# parents[2]: sound.py -> voice/src/voice(project) -> voice
_DEFAULT_SOUNDS_DIR = Path(__file__).parents[2] / "static" / "sounds"


class Earcon(StrEnum):
    WAKE = "wake"
    LISTENING = "listening"
    SUCCESS = "success"
    ERROR = "error"
    SLEEP = "sleep"


class SoundObserver(Observer):
    """Adds earcons to the agent lifecycle through the observer API."""

    def __init__(self, *, sounds_dir: Path | None = None) -> None:
        self._sounds_dir = sounds_dir or _DEFAULT_SOUNDS_DIR
        self._context: ObserverContext | None = None
        self._earcons: dict[Earcon, bytes] = {}

    async def prepare(self, context: ObserverContext) -> None:
        self._earcons = {
            earcon: (self._sounds_dir / f"{earcon}.wav").read_bytes()
            for earcon in Earcon
        }
        self._context = context

    async def on_wake_word_detected(
        self, name: str, score: float, sequence: int
    ) -> None:
        await self._play(Earcon.WAKE)

    async def on_user_inactivity_timeout(self, timeout_seconds: float) -> None:
        await self._play(Earcon.SLEEP)

    async def on_agent_stopped(self) -> None:
        await self._play(Earcon.SLEEP)

    async def _play(self, earcon: Earcon) -> None:
        if self._context is None:
            raise RuntimeError("SoundObserver must be prepared before use.")
        await self._context.audio_player.play(self._earcons[earcon])
