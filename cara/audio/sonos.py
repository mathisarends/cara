from __future__ import annotations

import asyncio
import functools
import logging
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

from pydantic_settings import BaseSettings, SettingsConfigDict

from cara.audio.ports import AudioPlayer

if TYPE_CHECKING:
    from soco import SoCo

logger = logging.getLogger(__name__)

# How long to wait for the speaker to actually start playing before giving up.
_PLAYBACK_START_TIMEOUT = 10.0


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


class _AudioClipServer:
    """Serves in-memory WAV clips over HTTP so Sonos devices can fetch them."""

    def __init__(self, host: str = "0.0.0.0", port: int = 0) -> None:
        self._clips: dict[str, bytes] = {}
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer((host, port), self._build_handler())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="cara-sonos-http",
            daemon=True,
        )
        self._thread.start()

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def add(self, audio: bytes) -> str:
        token = f"{uuid.uuid4().hex}.wav"
        with self._lock:
            self._clips[token] = audio
        return token

    def remove(self, token: str) -> None:
        with self._lock:
            self._clips.pop(token, None)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        clips = self._clips
        lock = self._lock

        class _Handler(BaseHTTPRequestHandler):
            def _lookup(self) -> bytes | None:
                with lock:
                    return clips.get(self.path.lstrip("/"))

            def _send_headers(self, audio: bytes) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(audio)))
                self.send_header("Accept-Ranges", "none")
                self.end_headers()

            def do_HEAD(self) -> None:  # noqa: N802 - http.server naming
                audio = self._lookup()
                if audio is None:
                    self.send_error(404)
                    return
                self._send_headers(audio)

            def do_GET(self) -> None:  # noqa: N802 - http.server naming
                audio = self._lookup()
                if audio is None:
                    self.send_error(404)
                    return
                self._send_headers(audio)
                self.wfile.write(audio)

            def log_message(self, fmt: str, *args: object) -> None:
                logger.debug("Sonos HTTP %s - %s", self.address_string(), fmt % args)

        return _Handler


class SonosAudioPlayer(AudioPlayer):
    """Plays WAV audio on a Sonos speaker via SoCo."""

    def __init__(
        self,
        *,
        device: SoCo | None = None,
        settings: SonosSettings | None = None,
    ) -> None:
        self._device = device
        self._settings = settings or SonosSettings()
        self._local_host = self._settings.local_host
        self._server: _AudioClipServer | None = None
        self._lock = threading.Lock()

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, functools.partial(self._play_sync, audio, cancel=cancel))

    def close(self) -> None:
        """Shut down the local HTTP server. Safe to call multiple times."""
        with self._lock:
            if self._server is not None:
                self._server.close()
                self._server = None

    def _play_sync(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        device = self._resolve_device()
        host = self._resolve_local_host(device)
        server = self._ensure_server()

        token = server.add(audio)
        uri = f"http://{host}:{server.port}/{token}"
        try:
            logger.info("Playing audio on Sonos %r via %s", device.player_name, uri)
            device.play_uri(uri, title="Cara")
            self._wait_until_finished(device, cancel=cancel)
        finally:
            server.remove(token)

    def _resolve_device(self) -> SoCo:
        if self._device is not None:
            return self._device
        if self._settings.ip_address:
            self._device = _load_soco()(self._settings.ip_address)
            return self._device
        discovery = _load_soco_discovery()
        if self._settings.speaker_name:
            device = discovery.by_name(self._settings.speaker_name)
            if device is None:
                raise RuntimeError(f"Sonos speaker {self._settings.speaker_name!r} not found on the network.")
        else:
            device = discovery.any_soco()
            if device is None:
                raise RuntimeError("No Sonos devices found on the network.")
        self._device = device
        return device

    def _resolve_local_host(self, device: SoCo) -> str:
        """Find the local IP that the Sonos device can reach us on."""
        if self._local_host:
            return self._local_host
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connecting a UDP socket performs no traffic but picks the routable
            # source address for the device's subnet.
            sock.connect((device.ip_address, 1400))
            self._local_host = sock.getsockname()[0]
        finally:
            sock.close()
        return self._local_host

    def _ensure_server(self) -> _AudioClipServer:
        with self._lock:
            if self._server is None:
                self._server = _AudioClipServer()
            return self._server

    def _wait_until_finished(self, device: SoCo, *, cancel: asyncio.Event | None = None) -> None:
        has_started = False
        start = time.monotonic()
        while True:
            if cancel is not None and cancel.is_set():
                logger.info("Sonos playback cancelled.")
                _safe_stop(device)
                return

            state = device.get_current_transport_info().get("current_transport_state")
            if state in ("PLAYING", "TRANSITIONING"):
                has_started = True
            elif has_started and state in ("STOPPED", "PAUSED_PLAYBACK"):
                return
            elif not has_started and time.monotonic() - start > _PLAYBACK_START_TIMEOUT:
                logger.warning("Sonos playback did not start within %.1fs.", _PLAYBACK_START_TIMEOUT)
                return

            time.sleep(self._settings.poll_interval)


def _safe_stop(device: SoCo) -> None:
    try:
        device.stop()
    except Exception:
        logger.exception("Failed to stop Sonos playback.")


def _load_soco() -> type[SoCo]:
    try:
        from soco import SoCo
    except ModuleNotFoundError as exc:
        raise RuntimeError("Sonos support requires the optional dependency group: `cara[sonos]`.") from exc
    return SoCo


def _load_soco_discovery() -> Any:
    try:
        import soco.discovery
    except ModuleNotFoundError as exc:
        raise RuntimeError("Sonos support requires the optional dependency group: `cara[sonos]`.") from exc
    return soco.discovery
