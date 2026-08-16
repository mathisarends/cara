import array
import asyncio
import logging
import sys

import pyaudio

from voice.audio.device import PortAudioDevice
from voice.audio.ports import AudioOutput

logger = logging.getLogger(__name__)

_DEFAULT_TRAILING_SILENCE_SECONDS = 0.2
_DEFAULT_VOLUME = 1.0
_MIN_VOLUME = 0.0
_MAX_VOLUME = 1.0
_BYTES_PER_SAMPLE = 2


def _apply_volume(chunk: bytes, volume: float) -> bytes:
    if volume >= 1.0:
        return chunk
    samples = array.array("h")
    samples.frombytes(chunk)
    if sys.byteorder == "big":
        samples.byteswap()
    for index, sample in enumerate(samples):
        samples[index] = max(-32768, min(32767, round(sample * volume)))
    if sys.byteorder == "big":
        samples.byteswap()
    return samples.tobytes()


class LocalAudioOutput(AudioOutput):
    """Streams raw PCM chunks through a local PortAudio output."""

    def __init__(
        self,
        *,
        trailing_silence_seconds: float = _DEFAULT_TRAILING_SILENCE_SECONDS,
        device: PortAudioDevice | None = None,
    ) -> None:
        if trailing_silence_seconds < 0:
            raise ValueError("trailing_silence_seconds must not be negative.")
        self._trailing_silence_seconds = trailing_silence_seconds
        self._device = device or PortAudioDevice()
        self._owns_device = device is None
        self._stream: pyaudio.Stream | None = None
        self._sample_rate: int | None = None
        self._channels: int | None = None
        self._volume = _DEFAULT_VOLUME
        self._writing = False

    @property
    def is_playing(self) -> bool:
        return self._writing

    async def start(self, *, sample_rate: int, channels: int) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if channels <= 0:
            raise ValueError("channels must be positive")
        if (
            self._stream is not None
            and self._sample_rate == sample_rate
            and self._channels == channels
        ):
            return
        self._close_stream()
        self._stream = self._device.open_stream(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            output=True,
        )
        self._sample_rate = sample_rate
        self._channels = channels

    async def stop(self) -> None:
        await self.clear_buffer()
        self._close_stream()
        if self._owns_device:
            self._device.close()

    async def play_chunk(self, chunk: bytes) -> None:
        if self._stream is None:
            raise RuntimeError("Audio output is not active.")
        self._writing = True
        try:
            await asyncio.to_thread(
                self._stream.write, _apply_volume(chunk, self._volume)
            )
        finally:
            self._writing = False

    async def finish_response(self) -> None:
        if not self._trailing_silence_seconds or self._sample_rate is None:
            return
        channels = self._channels or 1
        silence_frames = round(self._sample_rate * self._trailing_silence_seconds)
        await self.play_chunk(bytes(silence_frames * channels * _BYTES_PER_SAMPLE))

    async def clear_buffer(self) -> None:
        self._writing = False

    async def get_volume(self) -> float:
        return self._volume

    async def set_volume(self, volume: float) -> None:
        self._volume = max(_MIN_VOLUME, min(_MAX_VOLUME, volume))

    def _close_stream(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        stream.stop_stream()
        stream.close()
