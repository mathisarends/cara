import asyncio
import logging

from pydantic_settings import BaseSettings, SettingsConfigDict
from sonosify import (
    ClipPriority,
    ClipType,
    HostedAudioClip,
    SonosClient,
    SonosController,
)

from cara.audio.ports import AudioOutput, AudioSink

logger = logging.getLogger(__name__)

_MIN_VOLUME = 0.0
_MAX_VOLUME = 1.0
_CLIP_APP_ID = "cara"
_CLIP_NAME = "Cara"


class SonosSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SONOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    speaker_name: str | None = None
    ip_address: str | None = None
    local_host: str | None = None


class SonosAudioSink(AudioSink):
    """Plays WAV audio on a Sonos speaker through its local control API."""

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

    @property
    def output(self) -> AudioOutput:
        return AudioOutput.SONOS

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        if cancel is not None and cancel.is_set():
            return

        client = await self._resolve_client()
        logger.info("Playing audio clip on Sonos %s", client.ip)
        clip = await client.play_audio_clip_data(
            audio,
            local_host=self._settings.local_host,
            app_id=_CLIP_APP_ID,
            name=_CLIP_NAME,
            priority=ClipPriority.HIGH,
            clip_type=ClipType.CUSTOM,
        )
        try:
            await _wait_until_finished(clip, cancel)
        except asyncio.CancelledError:
            await asyncio.shield(clip.cancel())
            raise
        finally:
            clip.close()

    async def get_volume(self) -> float:
        client = await self._resolve_client()
        return await client.get_volume() / 100

    async def set_volume(self, volume: float) -> None:
        client = await self._resolve_client()
        level = round(max(_MIN_VOLUME, min(_MAX_VOLUME, volume)) * 100)
        await client.set_volume(level)

    async def close(self) -> None:
        """Close a lazily created Sonos client. Injected clients remain caller-owned."""
        if self._client is not None and self._owns_client:
            await self._client.close()
            self._client = None

    async def _resolve_client(self) -> SonosClient:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                controller = SonosController()
                self._client = await controller.client(
                    self._settings.speaker_name,
                    ip=self._settings.ip_address,
                )
            return self._client


async def _wait_until_finished(clip: HostedAudioClip, cancel: asyncio.Event | None) -> None:
    if cancel is None:
        await clip.wait_until_finished()
        return

    finished = asyncio.create_task(clip.wait_until_finished())
    interrupted = asyncio.create_task(cancel.wait())
    try:
        done, _ = await asyncio.wait((finished, interrupted), return_when=asyncio.FIRST_COMPLETED)
        if finished in done:
            await finished
        else:
            logger.info("Sonos playback cancelled.")
            await clip.cancel()
    finally:
        for task in (finished, interrupted):
            if not task.done():
                task.cancel()
        await asyncio.gather(finished, interrupted, return_exceptions=True)
