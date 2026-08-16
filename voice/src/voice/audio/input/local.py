import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

import pyaudio

from voice.audio.device import PortAudioDevice
from voice.audio.input.port import AudioInput

logger = logging.getLogger(__name__)

_INPUT_OVERFLOW_ERRNOS = (-9988, -9983)


class MicrophoneAudioInput(AudioInput):
    """Continuously captures PCM chunks from a local PortAudio input."""

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        channels: int = 1,
        frames_per_chunk: int = 1_280,
        device: PortAudioDevice | None = None,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if channels <= 0:
            raise ValueError("channels must be positive")
        if frames_per_chunk <= 0:
            raise ValueError("frames_per_chunk must be positive")
        self._sample_rate = sample_rate
        self._channels = channels
        self._frames_per_chunk = frames_per_chunk
        self._device = device or PortAudioDevice()
        self._owns_device = device is None
        self._stream: pyaudio.Stream | None = None
        self._active = False

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self) -> None:
        if self._active:
            return
        self._stream = self._open()
        self._active = True

    async def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        stream, self._stream = self._stream, None
        if stream is not None:
            if stream.is_active():
                stream.stop_stream()
            stream.close()
        if self._owns_device:
            self._device.close()

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        if not self._active:
            raise RuntimeError("Audio input is not active.")
        while self._active:
            yield await asyncio.to_thread(self._read_chunk)

    def _read_chunk(self) -> bytes:
        stream = self._stream
        if stream is None:
            raise RuntimeError("Audio input is not active.")
        try:
            return stream.read(self._frames_per_chunk, exception_on_overflow=False)
        except OSError as error:
            if error.errno not in _INPUT_OVERFLOW_ERRNOS:
                raise
            logger.warning("Audio input overflow - reopening stream.")
            self._reopen()
            return self._stream.read(
                self._frames_per_chunk, exception_on_overflow=False
            )

    def _open(self) -> pyaudio.Stream:
        return self._device.open_stream(
            rate=self._sample_rate,
            channels=self._channels,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self._frames_per_chunk,
        )

    def _reopen(self) -> None:
        with contextlib.suppress(Exception):
            if self._stream is not None:
                self._stream.close()
        self._stream = self._open()
