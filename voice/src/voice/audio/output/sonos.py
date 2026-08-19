import asyncio
import io
import logging
import wave
from contextlib import suppress

from sonosify import (
    AudioClip,
    ClipLEDBehavior,
    ClipPriority,
    ClipStatus,
    ClipType,
    HostedAudioClip,
    SonosClient,
)
from sonosify import SonosController as SonosifyController

from voice.audio.ports import AudioOutput
from voice.sonos import SonosSettings

logger = logging.getLogger(__name__)

_CLIP_APP_ID = "cara"
_CLIP_NAME = "Cara"
_BYTES_PER_SAMPLE = 2
_MIN_CLIP_DURATION_SECONDS = 1.5


class SonosOutput(AudioOutput):
    """Buffers PCM chunks and plays each completed response as a Sonos clip."""

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
        self._pcm = bytearray()
        self._active = False
        self._clip: HostedAudioClip | None = None
        self._playback_task: asyncio.Task[None] | None = None

    @property
    def is_playing(self) -> bool:
        return bool(self._pcm) or self._clip is not None

    async def start(self, *, sample_rate: int, channels: int) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if channels <= 0:
            raise ValueError("channels must be positive")
        await self._resolve_client()
        self._sample_rate = sample_rate
        self._channels = channels
        self._active = True

    async def stop(self) -> None:
        if not self._active and self._client is None:
            return
        await self.clear_buffer()
        if self._client is not None and self._owns_client:
            await self._client.close()
            self._client = None
        self._active = False

    async def play_chunk(self, chunk: bytes) -> None:
        if not self._active:
            raise RuntimeError("Audio output is not active.")
        self._pcm.extend(chunk)

    async def finish_response(self) -> None:
        if not self._active or not self._pcm:
            return
        sample_rate = self._sample_rate
        channels = self._channels
        if sample_rate is None or channels is None:
            raise RuntimeError("Audio output format is not configured.")

        pcm = bytes(self._pcm)
        self._pcm.clear()
        client = await self._resolve_client()
        audio = _wav(pcm, sample_rate=sample_rate, channels=channels)
        clip = await client.play_audio_clip_data(
            audio,
            local_host=self._settings.local_host,
            app_id=_CLIP_APP_ID,
            name=_CLIP_NAME,
            priority=ClipPriority.HIGH,
            clip_type=ClipType.CUSTOM,
            led_behavior=ClipLEDBehavior.WHITE_LED_QUICK_BREATHING,
        )
        result = await self._wait_for_clip(clip)
        if result.status is ClipStatus.DONE:
            return
        raise RuntimeError(
            "Sonos audio clip was not played: "
            f"fetched={clip.fetched} "
            f"result={result.model_dump(exclude_none=True)!r}"
        )

    async def _wait_for_clip(self, clip: HostedAudioClip) -> AudioClip:
        self._clip = clip
        self._playback_task = asyncio.current_task()
        try:
            return await clip.wait_until_finished()
        except asyncio.CancelledError:
            # This task is itself being cancelled, so cancelling the clip
            # must be shielded or the send would be cancelled before it goes out.
            await asyncio.shield(self._cancel_clip(clip))
            raise
        finally:
            if self._clip is clip:
                self._clip = None
            self._playback_task = None
            clip.close()

    async def clear_buffer(self) -> None:
        self._pcm.clear()
        clip, self._clip = self._clip, None
        if clip is not None:
            await self._cancel_clip(clip)

        task, self._playback_task = self._playback_task, None
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _cancel_clip(self, clip: HostedAudioClip) -> None:
        try:
            await clip.cancel()
        except Exception:
            logger.exception("Could not cancel Sonos audio clip.")

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


def _wav(pcm: bytes, *, sample_rate: int, channels: int) -> bytes:
    minimum_size = round(_MIN_CLIP_DURATION_SECONDS * sample_rate) * (
        channels * _BYTES_PER_SAMPLE
    )
    if len(pcm) < minimum_size:
        pcm += bytes(minimum_size - len(pcm))

    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(_BYTES_PER_SAMPLE)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()
