from enum import StrEnum
from pathlib import Path

from voice.events import (
    AudioPlaybackRequested,
    FollowUpTimedOut,
    SessionEnded,
    WakeWordDetected,
)
from voice.events.bus import EventBus

# parents[5]: sound_listener.py -> listener/events/voice/src/voice(project) -> cara
_DEFAULT_SOUNDS_DIR = Path(__file__).parents[5] / "static" / "sounds"


class Earcon(StrEnum):
    WAKE = "wake"
    LISTENING = "listening"
    SUCCESS = "success"
    ERROR = "error"
    SLEEP = "sleep"


class SoundListener:
    """Translates assistant lifecycle events into cached audio requests."""

    def __init__(self, event_bus: EventBus, *, sounds_dir: Path | None = None) -> None:
        self._event_bus = event_bus
        resolved_sounds_dir = sounds_dir or _DEFAULT_SOUNDS_DIR
        self._earcons: dict[Earcon, bytes] = {
            earcon: (resolved_sounds_dir / f"{earcon}.wav").read_bytes()
            for earcon in Earcon
        }

        event_bus.on(WakeWordDetected, self._on_wake_word_detected)
        event_bus.on(FollowUpTimedOut, self._on_follow_up_timed_out)
        event_bus.on(SessionEnded, self._on_session_ended)

    async def _on_wake_word_detected(self, event: WakeWordDetected) -> None:
        await self._request_playback(Earcon.WAKE)

    async def _on_follow_up_timed_out(self, event: FollowUpTimedOut) -> None:
        await self._request_playback(Earcon.SLEEP)

    async def _on_session_ended(self, event: SessionEnded) -> None:
        await self._request_playback(Earcon.SLEEP)

    async def _request_playback(self, earcon: Earcon) -> None:
        await self._event_bus.dispatch(
            AudioPlaybackRequested(audio=self._earcons[earcon])
        )
