import asyncio
import functools
import logging
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyaudio

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MicrophoneRecorderConfig:
    rate: int = 16000
    channels: int = 1
    chunk: int = 1024
    sample_width: int = 2
    silence_threshold: int = 500
    silence_seconds: float = 1.2
    min_record_seconds: float = 0.4
    max_record_seconds: float = 12.0
    output_dir: Path = Path(tempfile.gettempdir()) / "cara"


class MicrophoneRecorder:
    """Records one user utterance from the default microphone into a WAV file."""

    def __init__(self, config: MicrophoneRecorderConfig | None = None) -> None:
        self.config = config or MicrophoneRecorderConfig()

    async def record_until_silence(self) -> Path:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._record_until_silence_sync)

    def _record_until_silence_sync(self) -> Path:
        config = self.config
        pa = pyaudio.PyAudio()
        stream = pa.open(
            rate=config.rate,
            channels=config.channels,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=config.chunk,
        )
        frames: list[bytes] = []
        started_at = time.monotonic()
        silent_chunks = 0
        required_silent_chunks = max(1, int(config.silence_seconds * config.rate / config.chunk))

        logger.info("Recording user utterance...")
        try:
            while True:
                pcm = stream.read(config.chunk, exception_on_overflow=False)
                frames.append(pcm)

                elapsed = time.monotonic() - started_at
                rms = _rms_int16(pcm)
                if rms < config.silence_threshold and elapsed >= config.min_record_seconds:
                    silent_chunks += 1
                else:
                    silent_chunks = 0

                if silent_chunks >= required_silent_chunks:
                    break
                if elapsed >= config.max_record_seconds:
                    logger.info("Recording reached max duration of %.1fs.", config.max_record_seconds)
                    break
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

        config.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = config.output_dir / f"utterance-{int(time.time() * 1000)}.wav"
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(config.channels)
            wav.setsampwidth(config.sample_width)
            wav.setframerate(config.rate)
            wav.writeframes(b"".join(frames))

        logger.info("Recorded utterance to %s", output_path)
        return output_path


def _rms_int16(pcm: bytes) -> int:
    audio = np.frombuffer(pcm, dtype=np.int16)
    if audio.size == 0:
        return 0
    return int(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))


class WavAudioPlayer:
    """Plays WAV audio through the default output device."""

    async def play(self, audio_path: str | Path) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, functools.partial(self._play_sync, Path(audio_path)))

    def _play_sync(self, audio_path: Path) -> None:
        pa = pyaudio.PyAudio()
        try:
            with wave.open(str(audio_path), "rb") as wav:
                stream = pa.open(
                    format=pa.get_format_from_width(wav.getsampwidth()),
                    channels=wav.getnchannels(),
                    rate=wav.getframerate(),
                    output=True,
                )
                try:
                    while chunk := wav.readframes(1024):
                        stream.write(chunk)
                finally:
                    stream.stop_stream()
                    stream.close()
        finally:
            pa.terminate()
