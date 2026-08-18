import asyncio
import logging

from voice.audio.hub import AudioCursor, AudioHub
from voice.events import SessionStarted, UserAudioChunk
from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing

logger = logging.getLogger(__name__)


class UserAudioProducer:
    """Publishes every captured microphone frame for the lifetime of a session."""

    def __init__(self, *, event_bus: EventBus, audio_hub: AudioHub) -> None:
        self._event_bus = event_bus
        self._audio_hub = audio_hub
        self._cursor: AudioCursor | None = None
        self._task: asyncio.Task[None] | None = None
        self._closed = False

        event_bus.on(SessionStarted, self._on_session_started)
        event_bus.on(VoiceResourcesClosing, self._on_resources_closing)

    async def _on_session_started(self, _: SessionStarted) -> None:
        if self._closed or self._task is not None:
            return
        await self._audio_hub.start()
        self._cursor = await self._audio_hub.cursor()
        self._task = asyncio.create_task(
            self._publish(self._cursor),
            name="voice-user-audio",
        )

    async def _publish(self, cursor: AudioCursor) -> None:
        try:
            async for frame in cursor:
                await self._event_bus.dispatch(
                    UserAudioChunk(sequence=frame.sequence, chunk=frame.pcm)
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("User audio publisher failed")

    async def _on_resources_closing(self, _: VoiceResourcesClosing) -> None:
        if self._closed:
            return
        self._closed = True
        task, self._task = self._task, None
        cursor, self._cursor = self._cursor, None
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        if cursor is not None:
            await cursor.aclose()
        await self._audio_hub.stop()
