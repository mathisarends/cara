import asyncio
import logging

from voice.events import (
    AssistantResponseRequested,
    AssistantTurnStarted,
    SessionEnded,
    UserTranscriptionRequested,
    UserTurnStarted,
)
from voice.events.bus import EventBus
from voice.events.models import (
    PromptTurnRequested,
    VoiceTurnEnded,
    VoiceTurnFailed,
    VoiceTurnRequested,
    VoiceTurnStarted,
)

logger = logging.getLogger(__name__)

type _TurnInput = UserTranscriptionRequested | AssistantResponseRequested


class TurnCoordinator:
    """Owns voice-turn identity and cancellation without knowing about events."""

    def __init__(self) -> None:
        self._next_turn_id = 0
        self._active_turn_id: int | None = None
        self._active_task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def has_active_turn(self) -> bool:
        return self._active_turn_id is not None

    def start_turn(self) -> int:
        if self._closed:
            raise RuntimeError("Cannot start a voice turn after closing turn state.")
        if self.has_active_turn:
            raise RuntimeError("Cannot start a voice turn while another is active.")

        self._next_turn_id += 1
        self._active_turn_id = self._next_turn_id
        return self._next_turn_id

    def set_active_task(self, turn_id: int, task: asyncio.Task[None]) -> None:
        if self._active_turn_id != turn_id:
            raise RuntimeError(f"Voice turn {turn_id} is not active.")
        self._active_task = task

    async def cancel_active_turn(self) -> int | None:
        """Cancel the running turn and wait for its teardown to finish."""
        turn_id, task = self._active_turn_id, self._active_task
        if turn_id is None or task is None or task.done():
            return None
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return turn_id

    def end_turn(self, turn_id: int) -> bool:
        if self._active_turn_id != turn_id:
            return False
        self._active_turn_id = None
        self._active_task = None
        return True

    async def close(self) -> None:
        self._closed = True
        task = self._active_task
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class TurnListener:
    """Maps turn lifecycle events onto a shared :class:`TurnCoordinator`."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        coordinator: TurnCoordinator,
        command_pre_roll_seconds: float = 0.16,
        speech_start_timeout: float = 8.0,
    ) -> None:
        if speech_start_timeout <= 0:
            raise ValueError("speech_start_timeout must be positive")
        self._event_bus = event_bus
        self._coordinator = coordinator
        self._pre_roll = command_pre_roll_seconds
        self._speech_start_timeout = speech_start_timeout
        self._failure_signals: dict[int, asyncio.Future[None]] = {}

        event_bus.on(SessionEnded, self._on_session_ended)
        event_bus.on(VoiceTurnFailed, self._on_voice_turn_failed)

        event_bus.on_request(VoiceTurnRequested, self._on_turn_requested)
        event_bus.on_request(PromptTurnRequested, self._on_prompt_turn_requested)

    async def _on_session_ended(self, _: SessionEnded) -> None:
        await self._coordinator.close()

    async def _on_voice_turn_failed(self, event: VoiceTurnFailed) -> None:
        logger.error(
            "Voice turn %d failure event received: %s",
            event.turn_id,
            event.message,
        )
        signal = self._failure_signals.get(event.turn_id)
        if signal is not None and not signal.done():
            signal.set_result(None)

    async def _on_turn_requested(self, event: VoiceTurnRequested) -> None:
        turn_id = await self._claim_turn()
        if turn_id is None:
            return
        await self._event_bus.dispatch(UserTurnStarted())
        await self._start_turn(
            turn_id,
            UserTranscriptionRequested(
                turn_id=turn_id,
                sequence=event.sequence,
                pre_roll_seconds=self._pre_roll,
                speech_start_timeout=(
                    event.speech_start_timeout or self._speech_start_timeout
                ),
            ),
        )

    async def _on_prompt_turn_requested(self, event: PromptTurnRequested) -> None:
        turn_id = await self._claim_turn()
        if turn_id is None:
            return
        await self._event_bus.dispatch(AssistantTurnStarted())
        await self._start_turn(
            turn_id,
            AssistantResponseRequested(turn_id=turn_id, text=event.prompt),
        )

    async def _claim_turn(self) -> int | None:
        if self._coordinator.is_closed:
            return None
        if self._coordinator.has_active_turn:
            logger.debug("Ignoring voice turn request while another turn is active")
            return None

        turn_id = self._coordinator.start_turn()
        logger.info("Voice turn %d started", turn_id)
        await self._event_bus.dispatch(VoiceTurnStarted(turn_id=turn_id))
        return turn_id

    async def _start_turn(self, turn_id: int, request: _TurnInput) -> None:
        if self._coordinator.is_closed:
            self._coordinator.end_turn(turn_id)
            await self._event_bus.dispatch(VoiceTurnEnded(turn_id=turn_id))
            return

        task = asyncio.create_task(
            self._run_turn(turn_id, request),
            name=f"voice-turn-{turn_id}",
        )
        self._coordinator.set_active_task(turn_id, task)

    async def _run_turn(self, turn_id: int, request: _TurnInput) -> None:
        failure_signal = asyncio.get_running_loop().create_future()
        self._failure_signals[turn_id] = failure_signal
        try:
            await _request_until_failed(
                self._event_bus,
                turn_id,
                request,
                failure_signal,
            )
        except Exception as error:
            logger.exception("Voice turn %d failed", turn_id)
            await self._event_bus.dispatch(
                VoiceTurnFailed(turn_id=turn_id, message=str(error))
            )
        finally:
            self._failure_signals.pop(turn_id, None)
            if not failure_signal.done():
                failure_signal.cancel()
            if self._coordinator.end_turn(turn_id):
                logger.info("Voice turn %d ended", turn_id)
                await self._event_bus.dispatch(VoiceTurnEnded(turn_id=turn_id))


async def _request_until_failed(
    event_bus: EventBus,
    turn_id: int,
    request: _TurnInput,
    failure_signal: asyncio.Future[None],
) -> None:
    request_task = asyncio.create_task(
        event_bus.request(request),
        name=f"voice-turn-request-{turn_id}",
    )
    try:
        done, _ = await asyncio.wait(
            (request_task, failure_signal),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if failure_signal not in done:
            await request_task
    finally:
        if not request_task.done():
            request_task.cancel()
        await asyncio.gather(request_task, return_exceptions=True)
