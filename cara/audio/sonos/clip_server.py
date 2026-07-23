import logging
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)


class _Clip:
    def __init__(self, audio: bytes) -> None:
        self.audio = audio
        self.served = threading.Event()


class _AudioClipServer:
    """Serves in-memory WAV clips over HTTP so Sonos devices can fetch them."""

    def __init__(self, host: str = "0.0.0.0", port: int = 0) -> None:
        self._clips: dict[str, _Clip] = {}
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
            self._clips[token] = _Clip(audio)
        return token

    def remove(self, token: str) -> None:
        with self._lock:
            self._clips.pop(token, None)

    def wait_served(self, token: str, timeout: float) -> bool:
        """Block until the Sonos device has fetched the clip, or the timeout lapses."""
        with self._lock:
            clip = self._clips.get(token)
        if clip is None:
            return False
        return clip.served.wait(timeout)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        clips = self._clips
        lock = self._lock

        class _Handler(BaseHTTPRequestHandler):
            def _lookup(self) -> _Clip | None:
                with lock:
                    return clips.get(self.path.lstrip("/"))

            def _send_headers(self, audio: bytes) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(audio)))
                self.send_header("Accept-Ranges", "none")
                self.end_headers()

            def do_HEAD(self) -> None:  # noqa: N802 - http.server naming
                clip = self._lookup()
                if clip is None:
                    self.send_error(404)
                    return
                self._send_headers(clip.audio)

            def do_GET(self) -> None:  # noqa: N802 - http.server naming
                clip = self._lookup()
                if clip is None:
                    self.send_error(404)
                    return
                self._send_headers(clip.audio)
                self.wfile.write(clip.audio)
                clip.served.set()

            def log_message(self, fmt: str, *args: object) -> None:
                logger.debug("Sonos HTTP %s - %s", self.address_string(), fmt % args)

        return _Handler
