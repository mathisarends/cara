import asyncio
from enum import StrEnum
from pathlib import Path

from agent.events import SessionEnded
from voice.audio.output import AudioPlayback
from voice.events import FollowUpTimedOut, WakeWordDetected
from voice.events.bus import EventBus

# parents[5]: sound_listener.py -> listener/events/voice/src/voice(project) -> cara
_DEFAULT_SOUNDS_DIR = Path(__file__).parents[5] / "static" / "sounds"


class Earcon(StrEnum):
    WAKE = "wake"
    LISTENING = "listening"
    SUCCESS = "success"
    ERROR = "error"
    SLEEP = "sleep"


class EarconPlayer:
    """Plays cached earcons through the shared, echo-referenced audio path."""

    def __init__(
        self, player: AudioPlayback, *, sounds_dir: Path | None = None
    ) -> None:
        self._player = player
        resolved_sounds_dir = sounds_dir or _DEFAULT_SOUNDS_DIR
        self._cache: dict[Earcon, bytes] = {
            earcon: (resolved_sounds_dir / f"{earcon}.wav").read_bytes()
            for earcon in Earcon
        }

    async def play(
        self, earcon: Earcon, *, cancel: asyncio.Event | None = None
    ) -> None:
        await self._player.play(self._cache[earcon], cancel=cancel)


class SoundListener:
    """Plays earcons for assistant lifecycle events."""

    def __init__(self, event_bus: EventBus, earcons: EarconPlayer) -> None:
        self._earcons = earcons

        event_bus.on(WakeWordDetected, self._on_wake_word_detected)
        event_bus.on(FollowUpTimedOut, self._on_follow_up_timed_out)
        event_bus.on(SessionEnded, self._on_session_ended)

    async def _on_wake_word_detected(self, event: WakeWordDetected) -> None:
        await self._earcons.play(Earcon.WAKE)

    async def _on_follow_up_timed_out(self, event: FollowUpTimedOut) -> None:
        await self._earcons.play(Earcon.SLEEP)

    async def _on_session_ended(self, event: SessionEnded) -> None:
        await self._earcons.play(Earcon.SLEEP)
