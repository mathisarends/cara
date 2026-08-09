import threading

import pyaudio


class PortAudioDevice:
    """Owns the process-local PortAudio lifecycle for related audio streams."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pa: pyaudio.PyAudio | None = None
        self._closed = False

    def open_stream(self, **kwargs: object) -> pyaudio.Stream:
        with self._lock:
            return self._ensure_open().open(**kwargs)

    def get_format_from_width(self, width: int) -> int:
        with self._lock:
            return self._ensure_open().get_format_from_width(width)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._pa is not None:
                self._pa.terminate()

    def _ensure_open(self) -> pyaudio.PyAudio:
        if self._closed:
            raise RuntimeError("Audio device is closed.")
        if self._pa is None:
            self._pa = pyaudio.PyAudio()
        return self._pa
