import asyncio
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from hueify import Hueify

from room.features.voice.integrations.hue.room_lighting import HueRoomLighting
from room.features.voice.integrations.hue.state import LightingState
from voice.integrations import VoiceIntegration, VoiceIntegrationContext

logger = logging.getLogger(__name__)


class HueIntegration(VoiceIntegration):
    """Maps voice lifecycle events onto ambient Hue lighting states."""

    def __init__(
        self,
        room_name: str = "Mein Zimmer",
        *,
        hue: Hueify | None = None,
    ) -> None:
        self._lighting = HueRoomLighting(
            room_name=room_name,
            hue=hue or Hueify(),
        )
        self._jobs: asyncio.Queue[Callable[[], Awaitable[None]]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    async def prepare(self, context: VoiceIntegrationContext) -> None:
        await self._lighting.prepare()

    async def on_wake_word_detected(
        self, name: str, score: float, sequence: int
    ) -> None:
        self._submit_state(LightingState.LISTENING)

    async def on_user_turn_started(self) -> None:
        self._submit_state(LightingState.LISTENING)

    async def on_assistant_turn_started(self, turn_id: UUID) -> None:
        self._submit_state(LightingState.PROCESSING)

    async def on_assistant_tool_started(self, name: str) -> None:
        self._submit_state(LightingState.PROCESSING)

    async def on_assistant_tool_completed(self, name: str) -> None:
        self._submit_state(LightingState.PROCESSING)

    async def on_assistant_started_responding(self) -> None:
        self._submit_state(LightingState.SPEAKING)

    async def on_assistant_interrupted(self, turn_id: UUID) -> None:
        self._submit_state(LightingState.LISTENING)

    async def on_voice_conversation_ended(self, reason: str) -> None:
        self._submit_state(LightingState.IDLE)

    async def on_agent_error(self, turn_id: UUID, message: str) -> None:
        self._submit_state(LightingState.IDLE)

    async def on_voice_turn_timed_out(self, turn_id: UUID) -> None:
        self._submit_state(LightingState.IDLE)

    async def on_session_stopped(self) -> None:
        if not self._lighting.is_prepared:
            return
        self._submit_state(LightingState.IDLE)
        await self._jobs.join()
        await self._stop_worker()
        await self._lighting.close()

    def _submit_state(self, state: LightingState) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(
                self._run(), name="voice-hue-integration"
            )
        self._jobs.put_nowait(lambda: self._lighting.set_state(state))

    async def _run(self) -> None:
        while True:
            job = await self._jobs.get()
            try:
                await job()
            except Exception:
                logger.exception("Hue operation failed")
            finally:
                self._jobs.task_done()

    async def _stop_worker(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        await asyncio.gather(self._worker, return_exceptions=True)
        self._worker = None
