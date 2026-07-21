import asyncio
import logging
from enum import StrEnum
from pathlib import Path

from cara.audio.ports import AudioOutputStrategy

logger = logging.getLogger(__name__)

_DEFAULT_SOUNDS_DIR = Path(__file__).resolve().parent.parent.parent / "sounds"


class Earcon(StrEnum):
    WAKE = "wake"
    INTERRUPT = "interrupt"
    LISTENING = "listening"
    SUCCESS = "success"
    ERROR = "error"
    SLEEP = "sleep"


class EarconPlayer:
    def __init__(self, player: AudioOutputStrategy, *, sounds_dir: Path | None = None) -> None:
        self._player = player
        self._sounds_dir = sounds_dir or _DEFAULT_SOUNDS_DIR
        self._cache: dict[Earcon, bytes] = {}
        self._background: set[asyncio.Task[None]] = set()

    async def play(self, earcon: Earcon, *, cancel: asyncio.Event | None = None) -> None:
        await self._player.play(self._load(earcon), cancel=cancel)

    def play_soon(self, earcon: Earcon) -> None:
        """Schedule an earcon without blocking the caller."""
        task = asyncio.create_task(self._play_safely(earcon))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _play_safely(self, earcon: Earcon) -> None:
        try:
            await self.play(earcon)
        except Exception:
            logger.exception("Failed to play earcon %s", earcon)

    def _load(self, earcon: Earcon) -> bytes:
        cached = self._cache.get(earcon)
        if cached is None:
            cached = (self._sounds_dir / f"{earcon}.wav").read_bytes()
            self._cache[earcon] = cached
        return cached
