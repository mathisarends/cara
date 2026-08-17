import asyncio

from agent.events import SessionEnded, UserTurnStarted
from voice.audio.hub import AudioCursor, AudioHub
from voice.events.bus import EventBus
from voice.events.models import (
    VoiceTurnEnded,
    VoiceTurnFailed,
    VoiceTurnRequested,
)
from voice.pipeline.speech import SpeechPipeline


class TurnManager:
    """Owns voice-turn identity, cancellation, and capture cursor lifetime."""

    def __init__(
        self,
        *,
        audio_hub: AudioHub,
        pipeline: SpeechPipeline,
        event_bus: EventBus,
        command_pre_roll_seconds: float = 0.16,
        speech_start_timeout: float = 8.0,
    ) -> None:
        if speech_start_timeout <= 0:
            raise ValueError("speech_start_timeout must be positive")
        self._audio_hub = audio_hub
        self._pipeline = pipeline
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
        await self.interrupt()

    async def interrupt(self) -> bool:
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
        cursor = await self._cursor_for(event)
        self._next_turn_id += 1
        turn_id = self._next_turn_id
        self._active_turn_id = turn_id
        await self._event_bus.dispatch(UserTurnStarted())
        if self._closed:
            self._active_turn_id = None
            await cursor.aclose()
            await self._event_bus.dispatch(VoiceTurnEnded(turn_id=turn_id))
            return
        self._active_task = asyncio.create_task(
            self._run_turn(
                turn_id,
                cursor,
                event.speech_start_timeout or self._speech_start_timeout,
            ),
            name=f"voice-turn-{turn_id}",
        )

    async def _run_turn(
        self, turn_id: int, cursor: AudioCursor, speech_start_timeout: float
    ) -> None:
        try:
            await self._pipeline.run(
                turn_id=turn_id,
                audio=cursor,
                speech_start_timeout=speech_start_timeout,
            )
        except asyncio.CancelledError:
            raise
        except StopAsyncIteration:
            pass
        except Exception as error:
            await self._event_bus.dispatch(
                VoiceTurnFailed(turn_id=turn_id, message=str(error))
            )
        finally:
            await cursor.aclose()
            if self._active_turn_id == turn_id:
                self._active_turn_id = None
                self._active_task = None
                await self._event_bus.dispatch(VoiceTurnEnded(turn_id=turn_id))

    async def _cursor_for(self, event: VoiceTurnRequested) -> AudioCursor:
        if event.sequence is None:
            return await self._audio_hub.cursor()
        return await self._audio_hub.cursor_for_detection(
            event.sequence, pre_roll_seconds=self._pre_roll
        )
