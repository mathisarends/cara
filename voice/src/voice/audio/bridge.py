import asyncio
from collections.abc import AsyncIterator

from voice.audio.playback_coordinator import PlaybackCoordinator
from voice.audio.ports import AudioOutput
from voice.events import AssistantSpeechStarted
from voice.events.bus import EventBus
from voice.events.models import (
    AssistantAudioChunk,
    AssistantAudioCompleted,
    AssistantAudioStarted,
    AssistantPlaybackCompleted,
    AudioPlaybackRequested,
    VoiceResourcesClosing,
    VoiceTurnEnded,
    VoiceTurnFailed,
)

_END = object()


class AudioBridge:
    """Bridges assistant audio events to the physical output device."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        output_device: AudioOutput,
        playback_queue_size: int = 8,
    ) -> None:
        if playback_queue_size <= 0:
            raise ValueError("playback_queue_size must be positive")
        self._event_bus = event_bus
        self._playback = PlaybackCoordinator(output_device)
        self._playback_queue_size = playback_queue_size
        self._state_lock = asyncio.Lock()
        self._playback_task: asyncio.Task[None] | None = None
        self._audio_queue: asyncio.Queue[bytes | object] | None = None
        self._active_turn_id: int | None = None
        self._speech_started = False
        self._closed = False

        event_bus.on(AssistantAudioStarted, self._on_audio_started)
        event_bus.on(AssistantAudioChunk, self._on_audio_chunk)
        event_bus.on(AssistantAudioCompleted, self._on_audio_completed)
        event_bus.on(AudioPlaybackRequested, self._on_playback_requested)
        event_bus.on(VoiceTurnEnded, self._on_turn_ended)
        event_bus.on(VoiceResourcesClosing, self._on_resources_closing)

    async def _on_playback_requested(self, event: AudioPlaybackRequested) -> None:
        await self._playback.play(event.audio)

    async def _on_audio_started(self, event: AssistantAudioStarted) -> None:
        await self._stop_active_playback()
        queue: asyncio.Queue[bytes | object] = asyncio.Queue(self._playback_queue_size)
        async with self._state_lock:
            if self._closed:
                return
            self._active_turn_id = event.turn_id
            self._audio_queue = queue
            self._speech_started = False
            self._playback_task = asyncio.create_task(
                self._playback.stream(
                    _stream_chunks(queue),
                    sample_rate=event.sample_rate,
                    channels=event.channels,
                ),
                name=f"voice-audio-playback-{event.turn_id}",
            )

    async def _on_audio_chunk(self, event: AssistantAudioChunk) -> None:
        if not event.chunk:
            return
        async with self._state_lock:
            if event.turn_id != self._active_turn_id or self._audio_queue is None:
                return
            first_chunk = not self._speech_started
            self._speech_started = True
        if first_chunk:
            await self._event_bus.dispatch(AssistantSpeechStarted())
        await self._enqueue_audio(event.turn_id, event.chunk)

    async def _on_audio_completed(self, event: AssistantAudioCompleted) -> None:
        task, enqueued = await self._enqueue_audio(event.turn_id, _END)
        if task is None or not enqueued:
            return
        await self._finish_playback(event.turn_id, task, publish_completion=True)

    async def _enqueue_audio(
        self, turn_id: int, item: bytes | object
    ) -> tuple[asyncio.Task[None] | None, bool]:
        async with self._state_lock:
            if turn_id != self._active_turn_id or self._audio_queue is None:
                return None, False
            queue = self._audio_queue
            task = self._playback_task
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
        await self._finish_playback(turn_id, task, publish_completion=False)
        return task, False

    async def _finish_playback(
        self,
        turn_id: int,
        task: asyncio.Task[None],
        *,
        publish_completion: bool,
    ) -> None:
        results = await asyncio.gather(task, return_exceptions=True)
        async with self._state_lock:
            if task is not self._playback_task:
                return
            self._clear_playback_state()

        error = results[0]
        if isinstance(error, asyncio.CancelledError):
            return
        if isinstance(error, BaseException):
            await self._event_bus.dispatch(
                VoiceTurnFailed(turn_id=turn_id, message=str(error))
            )
            return
        if publish_completion:
            await self._event_bus.dispatch(AssistantPlaybackCompleted(turn_id=turn_id))

    async def _on_turn_ended(self, event: VoiceTurnEnded) -> None:
        await self._stop_active_playback(turn_id=event.turn_id)

    async def _on_resources_closing(self, _: VoiceResourcesClosing) -> None:
        if self._closed:
            return
        self._closed = True
        await self._stop_active_playback()
        await self._playback.interrupt()
        await self._playback.stop()

    async def _stop_active_playback(self, turn_id: int | None = None) -> None:
        async with self._state_lock:
            if turn_id is not None and turn_id != self._active_turn_id:
                return
            task = self._playback_task
            self._clear_playback_state()
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)

    def _clear_playback_state(self) -> None:
        self._playback_task = None
        self._audio_queue = None
        self._active_turn_id = None
        self._speech_started = False


async def _stream_chunks(
    queue: asyncio.Queue[bytes | object],
) -> AsyncIterator[bytes]:
    while True:
        item = await queue.get()
        if item is _END:
            return
        if isinstance(item, bytes):
            yield item
