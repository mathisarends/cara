import threading
from dataclasses import dataclass

import numpy as np
from aec_audio_processing import AudioProcessor

from cara.audio.ports import EchoCanceller


@dataclass(frozen=True)
class EchoCancellationSettings:
    sample_rate: int = 16000
    channels: int = 1
    stream_delay_ms: int = 50


class WebRtcEchoCanceller(EchoCanceller):
    """Processes microphone PCM against the audio currently sent to the speaker."""

    def __init__(self, settings: EchoCancellationSettings | None = None) -> None:
        self._settings = settings or EchoCancellationSettings()
        if self._settings.channels != 1:
            raise ValueError("WebRTC echo cancellation currently requires mono capture audio.")
        if not 0 <= self._settings.stream_delay_ms <= 500:
            raise ValueError("stream_delay_ms must be between 0 and 500.")

        self._processor = AudioProcessor(
            enable_aec=True,
            enable_ns=True,
            enable_agc=False,
            enable_vad=False,
        )
        self._processor.set_stream_format(self._settings.sample_rate, self._settings.channels)
        self._processor.set_reverse_stream_format(self._settings.sample_rate, self._settings.channels)
        self._processor.set_stream_delay(self._settings.stream_delay_ms)
        self._frame_bytes = self._processor.get_frame_size() * self._settings.channels * 2
        self._render_buffer = bytearray()
        self._lock = threading.Lock()

    @property
    def sample_rate(self) -> int:
        return self._settings.sample_rate

    @property
    def channels(self) -> int:
        return self._settings.channels

    def analyze_render(
        self,
        pcm: bytes,
        *,
        sample_rate: int,
        channels: int,
        sample_width: int,
    ) -> None:
        render_pcm = _to_mono_int16(
            pcm,
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
            target_rate=self._settings.sample_rate,
        )
        with self._lock:
            self._render_buffer.extend(render_pcm)
            while len(self._render_buffer) >= self._frame_bytes:
                frame = bytes(self._render_buffer[: self._frame_bytes])
                del self._render_buffer[: self._frame_bytes]
                self._processor.process_reverse_stream(frame)

    def process_capture(self, pcm: bytes) -> bytes:
        if len(pcm) % self._frame_bytes:
            raise ValueError(f"Capture PCM must contain complete {self._frame_bytes}-byte WebRTC frames.")
        with self._lock:
            return b"".join(
                self._processor.process_stream(pcm[offset : offset + self._frame_bytes])
                for offset in range(0, len(pcm), self._frame_bytes)
            )


def _to_mono_int16(
    pcm: bytes,
    *,
    sample_rate: int,
    channels: int,
    sample_width: int,
    target_rate: int,
) -> bytes:
    if channels < 1:
        raise ValueError("channels must be positive.")
    if sample_width != 2:
        raise ValueError("AEC render reference must use 16-bit PCM.")

    samples = np.frombuffer(pcm, dtype="<i2")
    if samples.size % channels:
        raise ValueError("PCM data does not contain complete audio frames.")
    if channels > 1:
        samples = np.rint(samples.reshape(-1, channels).astype(np.float64).mean(axis=1)).astype(np.int16)

    if sample_rate != target_rate and samples.size:
        target_size = round(samples.size * target_rate / sample_rate)
        source_positions = np.arange(samples.size, dtype=np.float64)
        target_positions = np.arange(target_size, dtype=np.float64) * sample_rate / target_rate
        samples = np.rint(np.interp(target_positions, source_positions, samples)).astype(np.int16)
    return samples.astype("<i2", copy=False).tobytes()
