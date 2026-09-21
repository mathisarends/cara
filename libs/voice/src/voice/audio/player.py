import asyncio
import io
import wave
from collections.abc import AsyncIterable, AsyncIterator, Callable

from voice.audio.ports import AudioOutput

_PLAYBACK_CHUNK_SECONDS = 0.01
_PCM_SAMPLE_WIDTH = 2


class AudioPlayer:
    """Serializes WAV and streaming PCM playback on one physical output."""

    def __init__(self, output: AudioOutput) -> None:
        self._output = output
        self._lock = asyncio.Lock()

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        wav_stream = _WavPcmStream(audio)
        async with self._lock:
            await self._play_stream(
                wav_stream,
                sample_rate=wav_stream.sample_rate,
                channels=wav_stream.channels,
                cancel=cancel,
            )

    async def stream(
        self,
        chunks: AsyncIterable[bytes],
        *,
        sample_rate: int,
        channels: int = 1,
        is_current: Callable[[], bool] | None = None,
        on_first_chunk: Callable[[], None] | None = None,
    ) -> None:
        async with self._lock:
            await self._play_stream(
                chunks,
                sample_rate=sample_rate,
                channels=channels,
                is_current=is_current,
                on_first_chunk=on_first_chunk,
            )

    async def interrupt(self) -> None:
        await self._output.clear_buffer()

    async def stop(self) -> None:
        await self._output.stop()

    async def _play_stream(
        self,
        chunks: AsyncIterable[bytes],
        *,
        sample_rate: int,
        channels: int = 1,
        cancel: asyncio.Event | None = None,
        is_current: Callable[[], bool] | None = None,
        on_first_chunk: Callable[[], None] | None = None,
    ) -> None:
        """Write raw PCM chunks to the output as they arrive."""
        await self._output.start(sample_rate=sample_rate, channels=channels)
        first = True
        try:
            async for chunk in chunks:
                if not chunk:
                    continue
                if cancel is not None and cancel.is_set():
                    await self._output.clear_buffer()
                    return
                if is_current is not None and not is_current():
                    await self._output.clear_buffer()
                    return
                if first:
                    first = False
                    if on_first_chunk is not None:
                        on_first_chunk()
                await self._output.play_chunk(chunk)
            if is_current is not None and not is_current():
                return
            await self._finish(cancel)
        except asyncio.CancelledError:
            await asyncio.shield(self._output.clear_buffer())
            raise

    async def _finish(self, cancel: asyncio.Event | None) -> None:
        if cancel is None:
            await self._output.finish_response()
            return

        finished = asyncio.create_task(self._output.finish_response())
        interrupted = asyncio.create_task(cancel.wait())
        try:
            done, _ = await asyncio.wait(
                (finished, interrupted), return_when=asyncio.FIRST_COMPLETED
            )
            if finished in done:
                await finished
            else:
                await self._output.clear_buffer()
        finally:
            for task in (finished, interrupted):
                if not task.done():
                    task.cancel()
            await asyncio.gather(finished, interrupted, return_exceptions=True)


class _WavPcmStream:
    """Validates a WAV container and exposes its PCM frames as async chunks."""

    def __init__(self, audio: bytes) -> None:
        self._audio = audio
        with wave.open(io.BytesIO(audio), "rb") as wav_file:
            if wav_file.getsampwidth() != _PCM_SAMPLE_WIDTH:
                raise ValueError("Audio outputs require signed 16-bit PCM WAV audio.")
            self._sample_rate = wav_file.getframerate()
            self._channels = wav_file.getnchannels()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self._chunks()

    async def _chunks(self) -> AsyncIterator[bytes]:
        with wave.open(io.BytesIO(self._audio), "rb") as wav_file:
            frames_per_chunk = max(
                1,
                round(self._sample_rate * _PLAYBACK_CHUNK_SECONDS),
            )
            while chunk := wav_file.readframes(frames_per_chunk):
                yield chunk
