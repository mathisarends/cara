from collections.abc import AsyncIterator

import numpy as np

from voice.audio.ports import AudioInput, AudioOutput
from voice.echo_cancellation.alignment import ReferenceAligner
from voice.echo_cancellation.ports import EchoCanceller
from voice.echo_cancellation.reference import PlaybackReference

_BYTES_PER_SAMPLE = 2


class ReferenceTapOutput(AudioOutput):
    def __init__(self, output: AudioOutput, reference: PlaybackReference):
        self._output = output
        self._reference = reference
        self._reference_sample_rate = reference.sample_rate
        self._output_sample_rate: int | None = None
        self._output_channels: int | None = None

    @property
    def is_playing(self) -> bool:
        return self._output.is_playing

    async def start(self, *, sample_rate: int, channels: int) -> None:
        self._reference.start_playback()
        self._output_sample_rate = sample_rate
        self._output_channels = channels
        await self._output.start(sample_rate=sample_rate, channels=channels)

    async def stop(self) -> None:
        await self._output.stop()

    async def play_chunk(self, chunk: bytes) -> None:
        sample_rate = self._output_sample_rate
        channels = self._output_channels
        if sample_rate is None or channels is None:
            raise RuntimeError("Audio output format is not configured.")
        self._reference.write(
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
        aligner: ReferenceAligner,
        canceller: EchoCanceller,
    ):
        self._input = input_device
        self._aligner = aligner
        self._canceller = canceller

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
        self._canceller.reset()
        self._aligner.reset()
        await self._input.start()

    async def stop(self) -> None:
        await self._input.stop()

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        async for chunk in self._input.stream_chunks():
            cleaned = self._canceller.process(chunk, self._aligner.read(chunk))
            if cleaned:
                yield cleaned
