import asyncio
import logging
import socket
import threading
import time

from pydantic_settings import BaseSettings, SettingsConfigDict
from sonosify import SonosClient, SonosController, TransportState

from cara.audio.ports import AudioOutput, AudioOutputStrategy
from cara.audio.sonos.clip_server import _AudioClipServer

logger = logging.getLogger(__name__)

# How long to wait for the speaker to actually start playing before giving up.
_PLAYBACK_START_TIMEOUT = 10.0
_MIN_VOLUME = 0.0
_MAX_VOLUME = 1.0


class SonosSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SONOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ip_address: str | None = None
    speaker_name: str | None = None
    local_host: str | None = None
    poll_interval: float = 0.25


class SonosAudioPlayer(AudioOutputStrategy):
    """Plays WAV audio on a Sonos speaker via sonosify."""

    def __init__(
        self,
        *,
        client: SonosClient | None = None,
        settings: SonosSettings | None = None,
    ) -> None:
        self._client = client
        self._settings = settings or SonosSettings()
        self._local_host = self._settings.local_host
        self._ip: str | None = None
        self._server: _AudioClipServer | None = None
        self._server_lock = threading.Lock()
        self._ip_lock = asyncio.Lock()

    @property
    def output(self) -> AudioOutput:
        return AudioOutput.SONOS

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        client = await self._resolve_client()
        host = self._resolve_local_host(client.ip)
        server = self._ensure_server()

        token = server.add(audio)
        uri = f"http://{host}:{server.port}/{token}"
        try:
            logger.info("Playing audio on Sonos %s via %s", client.ip, uri)
            await client.play_uri(uri, title="Cara")
            await self._wait_until_finished(client, cancel=cancel)
        finally:
            server.remove(token)

    async def get_volume(self) -> float:
        client = await self._resolve_client()
        return await client.get_volume() / 100

    async def set_volume(self, volume: float) -> None:
        client = await self._resolve_client()
        await client.set_volume(round(max(_MIN_VOLUME, min(_MAX_VOLUME, volume)) * 100))

    def close(self) -> None:
        """Shut down the local HTTP server. Safe to call multiple times."""
        with self._server_lock:
            if self._server is not None:
                self._server.close()
                self._server = None

    async def _resolve_client(self) -> SonosClient:
        if self._client is not None:
            return self._client
        async with self._ip_lock:
            if self._client is not None:
                return self._client
            self._client = SonosClient(await self._resolve_ip())
            return self._client

    async def _resolve_ip(self) -> str:
        if self._ip is not None:
            return self._ip
        if self._settings.ip_address:
            self._ip = self._settings.ip_address
            return self._ip
        system = await SonosController().discover()
        self._ip = system.find(self._settings.speaker_name).ip
        return self._ip

    def _resolve_local_host(self, device_ip: str) -> str:
        """Find the local IP that the Sonos device can reach us on."""
        if self._local_host:
            return self._local_host
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connecting a UDP socket performs no traffic but picks the routable
            # source address for the device's subnet.
            sock.connect((device_ip, 1400))
            self._local_host = sock.getsockname()[0]
        finally:
            sock.close()
        return self._local_host

    def _ensure_server(self) -> _AudioClipServer:
        with self._server_lock:
            if self._server is None:
                self._server = _AudioClipServer()
            return self._server

    async def _wait_until_finished(self, client: SonosClient, *, cancel: asyncio.Event | None = None) -> None:
        has_started = False
        start = time.monotonic()
        while True:
            if cancel is not None and cancel.is_set():
                logger.info("Sonos playback cancelled.")
                await _safe_stop(client)
                return

            state = (await client.get_transport_info()).state
            if state in (TransportState.PLAYING, TransportState.TRANSITIONING):
                has_started = True
            elif has_started and state in (TransportState.STOPPED, TransportState.PAUSED_PLAYBACK):
                return
            elif not has_started and time.monotonic() - start > _PLAYBACK_START_TIMEOUT:
                logger.warning("Sonos playback did not start within %.1fs.", _PLAYBACK_START_TIMEOUT)
                return

            await asyncio.sleep(self._settings.poll_interval)


async def _safe_stop(client: SonosClient) -> None:
    try:
        await client.stop()
    except Exception:
        logger.exception("Failed to stop Sonos playback.")
