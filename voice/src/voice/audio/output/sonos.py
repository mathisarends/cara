import asyncio
import logging
from contextlib import suppress

from sonosify import (
    AudioClip,
    AudioClipStream,
    ClipLEDBehavior,
    ClipPriority,
    ClipStatus,
    ClipType,
    SonosClient,
    streaming_wav_header,
)
from sonosify import SonosController as SonosifyController

from voice.audio.ports import AudioOutput
from voice.audio.volume import VolumeControl
from voice.sonos import SonosSettings

logger = logging.getLogger(__name__)

_CLIP_APP_ID = "cara"
_CLIP_NAME = "Cara"
_BYTES_PER_SAMPLE = 2
_MIN_CLIP_DURATION_SECONDS = 1.5
_MAX_CLIP_VOLUME = 100


class SonosOutput(AudioOutput, VolumeControl):
    """Streams PCM chunks to the speaker as a single growing Sonos clip."""

    def __init__(
        self,
        *,
        client: SonosClient | None = None,
        settings: SonosSettings | None = None,
    ) -> None:
        self._client = client
        self._settings = settings or SonosSettings()
        self._owns_client = client is None
        self._client_lock = asyncio.Lock()
        self._sample_rate: int | None = None
        self._channels: int | None = None
        self._stream: AudioClipStream | None = None
        self._pcm_bytes = 0
        self._active = False
        self._playback_task: asyncio.Task[None] | None = None

    @property
    def is_playing(self) -> bool:
        return self._stream is not None

    async def start(self, *, sample_rate: int, channels: int) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if channels <= 0:
            raise ValueError("channels must be positive")

        await self.clear_buffer()
        client = await self._resolve_client()
        frame_size = channels * _BYTES_PER_SAMPLE
        prebuffer_seconds = self._settings.clip_prebuffer_seconds
        stream = await client.stream_audio_clip(
            local_host=self._settings.local_host,
            app_id=_CLIP_APP_ID,
            name=_CLIP_NAME,
            volume=await self._clip_volume(client),
            priority=ClipPriority.HIGH,
            clip_type=ClipType.CUSTOM,
            led_behavior=ClipLEDBehavior.WHITE_LED_QUICK_BREATHING,
            prebuffer_bytes=round(prebuffer_seconds * sample_rate) * frame_size,
        )
        self._sample_rate = sample_rate
        self._channels = channels
        self._pcm_bytes = 0
        self._stream = stream
        self._active = True
        await stream.write(
            streaming_wav_header(sample_rate, channels, _BYTES_PER_SAMPLE)
        )

    async def stop(self) -> None:
        if not self._active and self._client is None:
            return
        await self.clear_buffer()
        if self._client is not None and self._owns_client:
            await self._client.close()
            self._client = None
        self._active = False

    async def play_chunk(self, chunk: bytes) -> None:
        if not self._active or self._stream is None:
            raise RuntimeError("Audio output is not active.")
        self._pcm_bytes += len(chunk)
        await self._stream.write(chunk)

    async def finish_response(self) -> None:
        stream = self._stream
        if not self._active or stream is None:
            return
        if self._pcm_bytes == 0:
            await self.clear_buffer()
            return

        await self._pad_to_minimum_duration(stream)
        await stream.end()
        result = await self._wait_for_clip(stream)
        if result.status is ClipStatus.DONE:
            return
        raise RuntimeError(
            "Sonos audio clip was not played: "
            f"fetched={stream.fetched} "
            f"result={result.model_dump(exclude_none=True)!r}"
        )

    async def clear_buffer(self) -> None:
        self._pcm_bytes = 0
        stream, self._stream = self._stream, None
        if stream is not None:
            await self._abort_stream(stream)

        task, self._playback_task = self._playback_task, None
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def get_volume(self) -> int:
        client = await self._resolve_client()
        return await client.get_volume()

    async def set_volume(self, volume: int) -> None:
        client = await self._resolve_client()
        await client.set_volume(volume)

    async def _pad_to_minimum_duration(self, stream: AudioClipStream) -> None:
        """Sonos discards clips that are shorter than roughly a second."""
        if self._sample_rate is None or self._channels is None:
            raise RuntimeError("Audio output format is not configured.")
        frame_size = self._channels * _BYTES_PER_SAMPLE
        minimum = round(_MIN_CLIP_DURATION_SECONDS * self._sample_rate) * frame_size
        if self._pcm_bytes >= minimum:
            return
        await stream.write(bytes(minimum - self._pcm_bytes))
        self._pcm_bytes = minimum

    async def _wait_for_clip(self, stream: AudioClipStream) -> AudioClip:
        self._playback_task = asyncio.current_task()
        try:
            return await stream.wait_until_finished()
        except asyncio.CancelledError:
            # This task is itself being cancelled, so aborting the stream must
            # be shielded or the cancel command would never go out.
            await asyncio.shield(self._abort_stream(stream))
            raise
        finally:
            if self._stream is stream:
                self._stream = None
            self._playback_task = None
            stream.close()

    async def _abort_stream(self, stream: AudioClipStream) -> None:
        try:
            await stream.abort()
        except Exception:
            logger.exception("Could not abort Sonos audio clip stream.")

    async def _clip_volume(self, client: SonosClient) -> int | None:
        """Raise the clip above whatever the speaker is currently set to."""
        boost = self._settings.clip_volume_boost
        if boost == 0:
            return None
        return min(await client.get_volume() + boost, _MAX_CLIP_VOLUME)

    async def _resolve_client(self) -> SonosClient:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                controller = SonosifyController()
                self._client = await controller.client(
                    self._settings.speaker_name,
                    ip=self._settings.ip_address,
                )
            return self._client
