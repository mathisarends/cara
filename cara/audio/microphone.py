import contextlib
import logging

import pyaudio

from cara.audio.device import PortAudioDevice

logger = logging.getLogger(__name__)

_INPUT_OVERFLOW_ERRNOS = (-9988, -9983)


class MicrophoneStream:
    """A single microphone input stream shared by all audio consumers.

    The device is opened on first read and then kept open and running for the
    process lifetime, so wake-word detection and utterance recording hand the
    microphone back and forth without ever re-initialising it - the capture
    never goes deaf between them.
    """

    def __init__(
        self,
        *,
        rate: int = 16000,
        channels: int = 1,
        frames_per_buffer: int = 1280,
        device: PortAudioDevice | None = None,
    ) -> None:
        self._rate = rate
        self._channels = channels
        self._frames_per_buffer = frames_per_buffer
        self._device = device or PortAudioDevice()
        self._owns_device = device is None
        self._stream: pyaudio.Stream | None = None
        self._closed = False

    @property
    def rate(self) -> int:
        return self._rate

    @property
    def channels(self) -> int:
        return self._channels

    def read(self, num_frames: int) -> bytes:
        stream = self._ensure_open()
        try:
            return stream.read(num_frames, exception_on_overflow=False)
        except OSError as err:
            if err.errno in _INPUT_OVERFLOW_ERRNOS:
                logger.warning("Audio stream closed - reopening...")
                self._reopen()
                return self._stream.read(num_frames, exception_on_overflow=False)
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._stream is not None:
            if self._stream.is_active():
                self._stream.stop_stream()
            self._stream.close()
        if self._owns_device:
            self._device.close()

    def _ensure_open(self) -> pyaudio.Stream:
        if self._closed:
            raise RuntimeError("Microphone is closed.")
        if self._stream is None:
            self._stream = self._open()
        return self._stream

    def _open(self) -> pyaudio.Stream:
        return self._device.open_stream(
            rate=self._rate,
            channels=self._channels,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self._frames_per_buffer,
        )

    def _reopen(self) -> None:
        with contextlib.suppress(Exception):
            if self._stream is not None:
                self._stream.close()
        self._stream = self._open()
