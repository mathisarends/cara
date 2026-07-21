import asyncio
import functools
import io
import logging
import wave

import pyaudio

from cara.audio.ports import AudioOutputStrategy, EchoCanceller

logger = logging.getLogger(__name__)

_DEFAULT_TRAILING_SILENCE_SECONDS = 0.2


class WavAudioPlayer(AudioOutputStrategy):
    """Plays WAV audio through the default output device."""

    def __init__(
        self,
        *,
        trailing_silence_seconds: float = _DEFAULT_TRAILING_SILENCE_SECONDS,
        echo_canceller: EchoCanceller | None = None,
    ) -> None:
        if trailing_silence_seconds < 0:
            raise ValueError("trailing_silence_seconds must not be negative.")
        self._trailing_silence_seconds = trailing_silence_seconds
        self._echo_canceller = echo_canceller

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, functools.partial(self._play_sync, audio, cancel=cancel))

    def _play_sync(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        pa = pyaudio.PyAudio()
        try:
            with wave.open(io.BytesIO(audio), "rb") as wav:
                sample_width = wav.getsampwidth()
                channels = wav.getnchannels()
                frame_rate = wav.getframerate()
                stream = pa.open(
                    format=pa.get_format_from_width(sample_width),
                    channels=channels,
                    rate=frame_rate,
                    output=True,
                )
                try:
                    cancelled = False
                    frames_per_chunk = max(1, round(frame_rate / 100))
                    while chunk := wav.readframes(frames_per_chunk):
                        if cancel is not None and cancel.is_set():
                            logger.info("Audio playback cancelled.")
                            cancelled = True
                            break
                        if self._echo_canceller is not None:
                            self._echo_canceller.analyze_render(
                                chunk,
                                sample_rate=frame_rate,
                                channels=channels,
                                sample_width=sample_width,
                            )
                        stream.write(chunk)
                    if cancel is not None and cancel.is_set():
                        cancelled = True
                    if not cancelled and self._trailing_silence_seconds:
                        silence_frames = round(frame_rate * self._trailing_silence_seconds)
                        silence = bytes(silence_frames * channels * sample_width)
                        if self._echo_canceller is not None:
                            self._echo_canceller.analyze_render(
                                silence,
                                sample_rate=frame_rate,
                                channels=channels,
                                sample_width=sample_width,
                            )
                        stream.write(silence)
                        logger.debug(
                            "Added %.0f ms trailing silence to WAV playback.",
                            self._trailing_silence_seconds * 1000,
                        )
                finally:
                    stream.stop_stream()
                    stream.close()
        finally:
            pa.terminate()
