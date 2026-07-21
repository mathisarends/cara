import array
import asyncio
import functools
import io
import logging
import sys
import wave

from cara.audio.device import PortAudioDevice
from cara.audio.ports import AudioOutput, AudioOutputStrategy

logger = logging.getLogger(__name__)

_DEFAULT_TRAILING_SILENCE_SECONDS = 0.2
_DEFAULT_VOLUME = 1.0
_MIN_VOLUME = 0.0
_MAX_VOLUME = 1.0


def _apply_volume(chunk: bytes, volume: float) -> bytes:
    """Scale a 16-bit PCM chunk to the given volume, from 0.0 (silent) to 1.0 (full)."""
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


class WavAudioPlayer(AudioOutputStrategy):
    """Plays WAV audio through the default output device."""

    def __init__(
        self,
        *,
        trailing_silence_seconds: float = _DEFAULT_TRAILING_SILENCE_SECONDS,
        device: PortAudioDevice | None = None,
    ) -> None:
        if trailing_silence_seconds < 0:
            raise ValueError("trailing_silence_seconds must not be negative.")
        self._trailing_silence_seconds = trailing_silence_seconds
        self._device = device
        self._volume = _DEFAULT_VOLUME

    @property
    def output(self) -> AudioOutput:
        return AudioOutput.LOCAL

    async def get_volume(self) -> float:
        return self._volume

    async def set_volume(self, volume: float) -> None:
        self._volume = max(_MIN_VOLUME, min(_MAX_VOLUME, volume))

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, functools.partial(self._play_sync, audio, cancel=cancel))

    def _play_sync(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        device = self._device or PortAudioDevice()
        try:
            with wave.open(io.BytesIO(audio), "rb") as wav:
                sample_width = wav.getsampwidth()
                channels = wav.getnchannels()
                frame_rate = wav.getframerate()
                stream = device.open_stream(
                    format=device.get_format_from_width(sample_width),
                    channels=channels,
                    rate=frame_rate,
                    output=True,
                )
                try:
                    cancelled = False
                    volume = self._volume
                    frames_per_chunk = max(1, round(frame_rate / 100))
                    while chunk := wav.readframes(frames_per_chunk):
                        if cancel is not None and cancel.is_set():
                            logger.info("Audio playback cancelled.")
                            cancelled = True
                            break
                        stream.write(_apply_volume(chunk, volume))
                    if cancel is not None and cancel.is_set():
                        cancelled = True
                    if not cancelled and self._trailing_silence_seconds:
                        silence_frames = round(frame_rate * self._trailing_silence_seconds)
                        silence = bytes(silence_frames * channels * sample_width)
                        stream.write(silence)
                        logger.debug(
                            "Added %.0f ms trailing silence to WAV playback.",
                            self._trailing_silence_seconds * 1000,
                        )
                finally:
                    stream.stop_stream()
                    stream.close()
        finally:
            if self._device is None:
                device.close()
