import asyncio
import logging
from collections.abc import AsyncIterator

from voice.events import (
    AssistantAudioChunk,
    AssistantAudioCompleted,
    AssistantAudioStarted,
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantTextCompleted,
    VoiceTurnFailed,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded
from voice.tts.port import TextToSpeech

logger = logging.getLogger(__name__)

_END = object()


class TextToSpeechBridge:
    """Consumes realtime assistant text events and publishes synthesized PCM."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        text_to_speech: TextToSpeech,
        sample_rate: int = 24_000,
        queue_size: int = 8,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        self._event_bus = event_bus
        self._text_to_speech = text_to_speech
        self._sample_rate = sample_rate
        self._queue_size = queue_size
        self._state_lock = asyncio.Lock()
        self._active_turn_id: int | None = None
        self._text_queue: asyncio.Queue[str | object] | None = None
        self._synthesis_task: asyncio.Task[None] | None = None

        event_bus.on(AssistantResponseStarted, self._on_response_started)
        event_bus.on(AssistantTextChunk, self._on_text_chunk)
        event_bus.on(AssistantTextCompleted, self._on_text_completed)
        event_bus.on(VoiceTurnEnded, self._on_turn_ended)

    async def _on_response_started(self, event: AssistantResponseStarted) -> None:
        await self._stop_active_synthesis()
        queue: asyncio.Queue[str | object] = asyncio.Queue(self._queue_size)
        async with self._state_lock:
            self._active_turn_id = event.turn_id
            self._text_queue = queue
            self._synthesis_task = asyncio.create_task(
                self._synthesize(event.turn_id, queue),
                name=f"voice-tts-{event.turn_id}",
            )

    async def _on_text_chunk(self, event: AssistantTextChunk) -> None:
        if event.chunk:
            await self._enqueue(event.turn_id, event.chunk)

    async def _on_text_completed(self, event: AssistantTextCompleted) -> None:
        task, enqueued = await self._enqueue(event.turn_id, _END)
        if task is not None and enqueued:
            await task

    async def _synthesize(
        self,
        turn_id: int,
        queue: asyncio.Queue[str | object],
    ) -> None:
        try:
            await self._event_bus.dispatch(
                AssistantAudioStarted(
                    turn_id=turn_id,
                    sample_rate=self._sample_rate,
                )
            )
            async for chunk in self._text_to_speech.synthesize(_stream_text(queue)):
                if chunk:
                    await self._event_bus.dispatch(
                        AssistantAudioChunk(turn_id=turn_id, chunk=chunk)
                    )
            await self._event_bus.dispatch(AssistantAudioCompleted(turn_id=turn_id))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Text-to-speech failed for voice turn %d", turn_id)
            await self._event_bus.dispatch(
                VoiceTurnFailed(turn_id=turn_id, message=str(error))
            )
        finally:
            task = asyncio.current_task()
            async with self._state_lock:
                if task is self._synthesis_task:
                    self._clear_synthesis_state()

    async def _enqueue(
        self, turn_id: int, item: str | object
    ) -> tuple[asyncio.Task[None] | None, bool]:
        async with self._state_lock:
            if turn_id != self._active_turn_id or self._text_queue is None:
                return None, False
            queue = self._text_queue
            task = self._synthesis_task
        if task is None:
            return None, False

        enqueue = asyncio.create_task(queue.put(item))
        try:
            done, _ = await asyncio.wait(
                (enqueue, task), return_when=asyncio.FIRST_COMPLETED
            )
        except asyncio.CancelledError:
            enqueue.cancel()
            await asyncio.gather(enqueue, return_exceptions=True)
            raise
        if enqueue in done:
            await enqueue
            return task, True

        enqueue.cancel()
        await asyncio.gather(enqueue, return_exceptions=True)
        return task, False

    async def _on_turn_ended(self, event: VoiceTurnEnded) -> None:
        await self._stop_active_synthesis(turn_id=event.turn_id)

    async def _stop_active_synthesis(self, turn_id: int | None = None) -> None:
        async with self._state_lock:
            if turn_id is not None and turn_id != self._active_turn_id:
                return
            task = self._synthesis_task
            self._clear_synthesis_state()
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)

    def _clear_synthesis_state(self) -> None:
        self._active_turn_id = None
        self._text_queue = None
        self._synthesis_task = None


async def _stream_text(queue: asyncio.Queue[str | object]) -> AsyncIterator[str]:
    while True:
        item = await queue.get()
        if item is _END:
            return
        if isinstance(item, str):
            yield item
