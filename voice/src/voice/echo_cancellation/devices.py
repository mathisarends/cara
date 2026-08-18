import time
from collections.abc import AsyncIterator

import numpy as np

from voice.audio.ports import AudioInput, AudioOutput
from voice.echo_cancellation.ports import Clock, EchoCanceller
from voice.echo_cancellation.timeline import PlaybackTimeline

_BYTES_PER_SAMPLE = 2


class ReferenceTapOutput(AudioOutput):
    def __init__(self, output: AudioOutput, timeline: PlaybackTimeline):
        self._output = output
        self._timeline = timeline
        self._reference_sample_rate = timeline.sample_rate
        self._output_sample_rate: int | None = None
        self._output_channels: int | None = None

    @property
    def is_playing(self) -> bool:
        return self._output.is_playing

    async def start(self, *, sample_rate: int, channels: int) -> None:
        self._timeline.reset()
        self._output_sample_rate = sample_rate
        self._output_channels = channels
        await self._output.start(sample_rate=sample_rate, channels=channels)

    async def stop(self) -> None:
        await self._output.stop()
        self._timeline.reset()

    async def play_chunk(self, chunk: bytes) -> None:
        sample_rate = self._output_sample_rate
        channels = self._output_channels
        if sample_rate is None or channels is None:
            raise RuntimeError("Audio output format is not configured.")
        self._timeline.write(
            _reference_pcm(
                chunk,
                sample_rate=sample_rate,
                channels=channels,
                reference_sample_rate=self._reference_sample_rate,
            )
        )
        await self._output.play_chunk(chunk)

    async def finish_response(self) -> None:
        await self._output.finish_response()

    async def clear_buffer(self) -> None:
        await self._output.clear_buffer()
        self._timeline.discard_pending()


def _reference_pcm(
    chunk: bytes,
    *,
    sample_rate: int,
    channels: int,
    reference_sample_rate: int,
) -> bytes:
    frame_width = _BYTES_PER_SAMPLE * channels
    if len(chunk) % frame_width:
        raise ValueError("PCM chunks must contain complete audio frames.")

    frames = np.frombuffer(chunk, dtype="<i2").reshape(-1, channels)
    mono = frames.astype(np.float64).mean(axis=1)
    if sample_rate != reference_sample_rate and len(mono) > 0:
        output_frames = round(len(mono) * reference_sample_rate / sample_rate)
        positions = np.arange(output_frames) * sample_rate / reference_sample_rate
        mono = np.interp(positions, np.arange(len(mono)), mono)

    return np.clip(mono, -32768, 32767).astype("<i2").tobytes()


class EchoCancellingInput(AudioInput):
    def __init__(
        self,
        input_device: AudioInput,
        timeline: PlaybackTimeline,
        canceller: EchoCanceller,
        *,
        sample_rate: int = 24000,
        alignment_margin_s: float = 0.04,
        resync_threshold_s: float = 0.1,
        clock: Clock = time.monotonic,
    ):
        self._input = input_device
        self._timeline = timeline
        self._canceller = canceller
        self._sample_rate = sample_rate
        self._alignment_margin_s = alignment_margin_s
        self._resync_threshold_s = resync_threshold_s
        self._clock = clock
        self._capture_cursor: float | None = None

    @property
    def sample_rate(self) -> int:
        return self._input.sample_rate

    @property
    def channels(self) -> int:
        return self._input.channels

    @property
    def frames_per_chunk(self) -> int:
        return self._input.frames_per_chunk

    @property
    def is_active(self) -> bool:
        return self._input.is_active

    async def start(self) -> None:
        self._capture_cursor = None
        self._canceller.reset()
        await self._input.start()

    async def stop(self) -> None:
        await self._input.stop()

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        async for chunk in self._input.stream_chunks():
            cleaned = self._canceller.process(chunk, self._reference_for(chunk))
            if cleaned:
                yield cleaned

    def _reference_for(self, chunk: bytes) -> bytes:
        samples = len(chunk) // _BYTES_PER_SAMPLE
        duration = samples / self._sample_rate
        start = self._capture_start(self._clock() - duration, duration)

        # Capture latency can only make the estimate late, so looking back is safe.
        return self._timeline.read(start - self._alignment_margin_s, samples)

    def _capture_start(self, estimate: float, duration: float) -> float:
        cursor = self._capture_cursor

        # Sample time ignores scheduler jitter; wall time still corrects real drift.
        if cursor is None or abs(cursor - estimate) > self._resync_threshold_s:
            cursor = estimate

        self._capture_cursor = cursor + duration
        return cursor
