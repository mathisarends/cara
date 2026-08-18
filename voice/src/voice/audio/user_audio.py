import asyncio
import logging

from voice.audio.buffered_input import AudioReader, BufferedAudioInput
from voice.events import SessionStarted, UserAudioChunk
from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing

logger = logging.getLogger(__name__)


class UserAudioProducer:
    """Publishes every captured microphone frame for the lifetime of a session."""

    def __init__(
        self, *, event_bus: EventBus, buffered_audio_input: BufferedAudioInput
    ) -> None:
        self._event_bus = event_bus
        self._buffered_audio_input = buffered_audio_input
        self._reader: AudioReader | None = None
        self._task: asyncio.Task[None] | None = None
        self._closed = False

        event_bus.on(SessionStarted, self._on_session_started)
        event_bus.on(VoiceResourcesClosing, self._on_resources_closing)

    async def _on_session_started(self, _: SessionStarted) -> None:
        if self._closed or self._task is not None:
            return
        await self._buffered_audio_input.start()
        self._reader = await self._buffered_audio_input.open_reader()
        self._task = asyncio.create_task(
            self._publish(self._reader),
            name="voice-user-audio",
        )

    async def _publish(self, reader: AudioReader) -> None:
        try:
            async for frame in reader:
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
        reader, self._reader = self._reader, None
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        if reader is not None:
            await reader.aclose()
        await self._buffered_audio_input.stop()
