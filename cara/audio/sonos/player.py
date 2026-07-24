import asyncio
import io
import logging
import socket
import threading
import time
import wave

from pydantic_settings import BaseSettings, SettingsConfigDict
from sonosify import ClipPriority, ClipType, SonosCloudAuth, SonosCloudClient

from cara.audio.ports import AudioOutput, AudioOutputStrategy
from cara.audio.sonos.clip_server import _AudioClipServer
from cara.audio.sonos.volume_monitor import SonosVolumeMonitor

logger = logging.getLogger(__name__)

# How long to wait for the speaker to fetch the clip before giving up.
_CLIP_FETCH_TIMEOUT = 10.0
_MIN_VOLUME = 0.0
_MAX_VOLUME = 1.0
_CLIP_NAME = "Cara"


class SonosSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SONOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    speaker_name: str | None = None
    speaker_host: str | None = None
    local_host: str | None = None
    poll_interval: float = 0.25


class SonosAudioPlayer(AudioOutputStrategy):
    """Plays WAV audio on a Sonos speaker via the Sonos cloud control API."""

    def __init__(
        self,
        *,
        client: SonosCloudClient | None = None,
        settings: SonosSettings | None = None,
    ) -> None:
        self._client = client
        self._settings = settings or SonosSettings()
        self._local_host = self._settings.local_host
        self._player_id: str | None = None
        self._server: _AudioClipServer | None = None
        self._server_lock = threading.Lock()
        self._player_lock = asyncio.Lock()
        self._volume_monitor: SonosVolumeMonitor | None = None
        self._volume_monitor_lock = asyncio.Lock()

    @property
    def output(self) -> AudioOutput:
        return AudioOutput.SONOS

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        if cancel is not None and cancel.is_set():
            return
        await self._resolve_volume_monitor()
        client = self._resolve_client()
        player_id = await self._resolve_player_id(client)
        host = self._resolve_local_host()
        server = self._ensure_server()

        token = server.add(audio)
        uri = f"http://{host}:{server.port}/{token}"
        try:
            logger.info("Playing audio clip on Sonos %s via %s", player_id, uri)
            clip = await client.play_audio_clip(
                player_id,
                uri,
                name=_CLIP_NAME,
                priority=ClipPriority.HIGH,
                clip_type=ClipType.CUSTOM,
            )
            if await self._wait_until_finished(audio, server, token, cancel=cancel):
                await _cancel_clip(client, player_id, clip.id)
        finally:
            server.remove(token)

    async def get_volume(self) -> float:
        monitor = await self._resolve_volume_monitor()
        if monitor is not None and monitor.volume is not None:
            return monitor.volume
        client = self._resolve_client()
        player_id = await self._resolve_player_id(client)
        return (await client.get_player_volume(player_id)).volume / 100

    async def set_volume(self, volume: float) -> None:
        await self._resolve_volume_monitor()
        client = self._resolve_client()
        player_id = await self._resolve_player_id(client)
        level = round(max(_MIN_VOLUME, min(_MAX_VOLUME, volume)) * 100)
        await client.set_player_volume(player_id, volume=level)

    async def close(self) -> None:
        """Shut down the local HTTP server and volume monitor. Safe to call multiple times."""
        with self._server_lock:
            if self._server is not None:
                self._server.close()
                self._server = None
        if self._volume_monitor is not None:
            await self._volume_monitor.stop()
            self._volume_monitor = None

    def _resolve_client(self) -> SonosCloudClient:
        if self._client is None:
            self._client = SonosCloudClient(SonosCloudAuth.from_environment())
        return self._client

    async def _resolve_player_id(self, client: SonosCloudClient) -> str:
        if self._player_id is not None:
            return self._player_id
        async with self._player_lock:
            if self._player_id is not None:
                return self._player_id
            if not self._settings.speaker_name:
                raise ValueError("SONOS_SPEAKER_NAME must be set to target a Sonos speaker")
            player = await client.resolve_player(self._settings.speaker_name)
            self._player_id = player.id
            return self._player_id

    def _resolve_local_host(self) -> str:
        """Find the local IP the Sonos speaker can fetch audio clips from."""
        if self._local_host:
            return self._local_host
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connecting a UDP socket performs no traffic but picks the routable
            # source address for the default (LAN) interface.
            sock.connect(("8.8.8.8", 80))
            self._local_host = sock.getsockname()[0]
        finally:
            sock.close()
        return self._local_host

    async def _resolve_volume_monitor(self) -> SonosVolumeMonitor | None:
        """Lazily start the local volume monitor, if a speaker host is configured."""
        if not self._settings.speaker_host:
            return None
        if self._volume_monitor is not None:
            return self._volume_monitor
        async with self._volume_monitor_lock:
            if self._volume_monitor is None:
                monitor = SonosVolumeMonitor(self._settings.speaker_host)
                await monitor.start()
                self._volume_monitor = monitor
            return self._volume_monitor

    def _ensure_server(self) -> _AudioClipServer:
        with self._server_lock:
            if self._server is None:
                self._server = _AudioClipServer()
            return self._server

    async def _wait_until_finished(
        self,
        audio: bytes,
        server: _AudioClipServer,
        token: str,
        *,
        cancel: asyncio.Event | None = None,
    ) -> bool:
        """Wait for the clip to finish; return whether it was cancelled early."""
        poll = self._settings.poll_interval
        started = time.monotonic()
        while not server.was_served(token):
            if cancel is not None and cancel.is_set():
                logger.info("Sonos playback cancelled.")
                return True
            if time.monotonic() - started > _CLIP_FETCH_TIMEOUT:
                logger.warning("Sonos did not fetch the audio clip within %.1fs.", _CLIP_FETCH_TIMEOUT)
                return False
            await asyncio.sleep(poll)

        end = time.monotonic() + _wav_duration(audio)
        while (remaining := end - time.monotonic()) > 0:
            if cancel is not None and cancel.is_set():
                logger.info("Sonos playback cancelled.")
                return True
            await asyncio.sleep(min(remaining, poll))
        return False


async def _cancel_clip(client: SonosCloudClient, player_id: str, clip_id: str) -> None:
    try:
        await client.cancel_audio_clip(player_id, clip_id)
    except Exception:
        logger.exception("Failed to cancel Sonos audio clip.")


def _wav_duration(audio: bytes) -> float:
    with wave.open(io.BytesIO(audio), "rb") as wav:
        rate = wav.getframerate()
        frame_size = wav.getnchannels() * wav.getsampwidth()
        declared = wav.getnframes()
    if rate <= 0 or frame_size <= 0:
        return 0.0
    # Streaming WAV headers (e.g. OpenAI TTS) can declare a bogus frame count,
    # so bound it by the frames that actually fit in the payload.
    available = len(audio) // frame_size
    return min(declared, available) / rate
