import asyncio
import logging

from voice.events import SessionEnded, UserTranscriptionRequested, UserTurnStarted
from voice.events.bus import EventBus
from voice.events.models import (
    VoiceTurnEnded,
    VoiceTurnRequested,
)

logger = logging.getLogger(__name__)


class TurnManager:
    """Owns voice-turn identity, cancellation, and lifecycle events."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        command_pre_roll_seconds: float = 0.16,
        speech_start_timeout: float = 8.0,
    ) -> None:
        if speech_start_timeout <= 0:
            raise ValueError("speech_start_timeout must be positive")
        self._event_bus = event_bus
        self._pre_roll = command_pre_roll_seconds
        self._speech_start_timeout = speech_start_timeout
        self._next_turn_id = 0
        self._active_turn_id: int | None = None
        self._active_task: asyncio.Task[None] | None = None
        self._closed = False

        event_bus.on(VoiceTurnRequested, self._on_turn_requested)
        event_bus.on(SessionEnded, self._on_session_ended)

    @property
    def has_active_turn(self) -> bool:
        return self._active_task is not None and not self._active_task.done()

    async def close(self) -> None:
        self._closed = True
        await self._cancel_active_turn()

    async def _cancel_active_turn(self) -> bool:
        task = self._active_task
        if task is None or task.done():
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def _on_session_ended(self, _: SessionEnded) -> None:
        await self.close()

    async def _on_turn_requested(self, event: VoiceTurnRequested) -> None:
        if self._closed:
            return
        if self.has_active_turn:
            raise RuntimeError("Cannot start a voice turn while another is active.")
        self._next_turn_id += 1
        turn_id = self._next_turn_id
        self._active_turn_id = turn_id
        logger.info("Voice turn %d started", turn_id)
        await self._event_bus.dispatch(UserTurnStarted())
        if self._closed:
            self._active_turn_id = None
            await self._event_bus.dispatch(VoiceTurnEnded(turn_id=turn_id))
            return
        self._active_task = asyncio.create_task(
            self._run_turn(
                UserTranscriptionRequested(
                    turn_id=turn_id,
                    sequence=event.sequence,
                    pre_roll_seconds=self._pre_roll,
                    speech_start_timeout=(
                        event.speech_start_timeout or self._speech_start_timeout
                    ),
                )
            ),
            name=f"voice-turn-{turn_id}",
        )

    async def _run_turn(self, request: UserTranscriptionRequested) -> None:
        turn_id = request.turn_id
        try:
            await self._event_bus.dispatch(request)
        finally:
            if self._active_turn_id == turn_id:
                self._active_turn_id = None
                self._active_task = None
                logger.info("Voice turn %d ended", turn_id)
                await self._event_bus.dispatch(VoiceTurnEnded(turn_id=turn_id))
