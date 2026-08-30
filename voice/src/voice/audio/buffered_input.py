from __future__ import annotations

import asyncio
import math
from collections import deque
from collections.abc import AsyncIterator

from voice.audio.models import AudioFormat, AudioFrame
from voice.audio.ports import AudioInput


class AudioOverrunError(RuntimeError):
    """Raised when a consumer falls behind the bounded capture history."""


class AudioReader:
    def __init__(
        self,
        buffered_input: BufferedAudioInput,
        next_sequence: int,
        pending: tuple[AudioFrame, ...] = (),
    ) -> None:
        self._buffered_input = buffered_input
        self._next_sequence = next_sequence
        self._pending = deque(pending)
        self._closed = False

    def __aiter__(self) -> AsyncIterator[AudioFrame]:
        return self

    async def __anext__(self) -> AudioFrame:
        if self._closed:
            raise StopAsyncIteration
        if self._pending:
            frame = self._pending.popleft()
            self._next_sequence = frame.sequence + 1
            return frame
        frame = await self._buffered_input._read(self._next_sequence)
        if frame is None:
            self._closed = True
            raise StopAsyncIteration
        self._next_sequence += 1
        return frame

    async def aclose(self) -> None:
        self._closed = True


class BufferedAudioInput:
    """Buffers one audio input and exposes independent readers over its frames."""

    def __init__(
        self,
        input_device: AudioInput,
        *,
        history_seconds: float = 2.0,
    ) -> None:
        if history_seconds <= 0:
            raise ValueError("history_seconds must be positive")
        self._input = input_device
        self._format = AudioFormat(
            sample_rate=input_device.sample_rate,
            channels=input_device.channels,
        )
        self._capacity = max(1, self._chunks_for(history_seconds))
        self._frames: deque[AudioFrame] = deque(maxlen=self._capacity)
        self._condition = asyncio.Condition()
        self._next_sequence = 0
        self._capture_task: asyncio.Task[None] | None = None
        self._failure: BaseException | None = None
        self._running = False

    @property
    def format(self) -> AudioFormat:
        return self._format

    @property
    def sample_rate(self) -> int:
        return self._format.sample_rate

    @property
    def channels(self) -> int:
        return self._format.channels

    @property
    def chunk_seconds(self) -> float:
        """Audio duration one chunk represents, unaffected by processing delays."""
        return self._input.frames_per_chunk / self._format.sample_rate

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        await self._input.start()
        self._running = True
        self._failure = None
        self._capture_task = asyncio.create_task(
            self._capture(), name="voice-audio-capture"
        )

    async def stop(self) -> None:
        if not self._running and self._capture_task is None:
            return
        self._running = False
        task, self._capture_task = self._capture_task, None
        await self._input.stop()
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with self._condition:
            self._condition.notify_all()

    async def open_reader(
        self,
        *,
        from_sequence: int | None = None,
        pre_roll_seconds: float = 0.0,
    ) -> AudioReader:
        """Open a reader on the live tail, or on ``from_sequence`` minus pre-roll.

        A start older than the retained history is clamped to the oldest frame.
        Retained start frames are copied into the reader so provider startup cannot
        evict them before consumption begins.
        """
        async with self._condition:
            if from_sequence is None:
                return AudioReader(self, self._next_sequence)
            start = from_sequence - max(self._chunks_for(pre_roll_seconds) - 1, 0)
            start = max(start, self._oldest_sequence)
            offset = start - self._oldest_sequence
            pending = tuple(self._frames)[offset:]
            return AudioReader(self, start, pending)

    async def _capture(self) -> None:
        try:
            async for pcm in self._input.stream_chunks():
                frame = AudioFrame(self._next_sequence, pcm)
                async with self._condition:
                    self._frames.append(frame)
                    self._next_sequence += 1
                    self._condition.notify_all()
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            self._failure = error
        finally:
            self._running = False
            async with self._condition:
                self._condition.notify_all()

    async def _read(self, sequence: int) -> AudioFrame | None:
        async with self._condition:
            while True:
                oldest = self._oldest_sequence
                if sequence < oldest:
                    raise AudioOverrunError(
                        f"reader fell behind: {sequence} < retained {oldest}"
                    )
                if sequence < self._next_sequence:
                    return self._frames[sequence - oldest]
                if self._failure is not None:
                    raise self._failure
                if not self._running:
                    return None
                await self._condition.wait()

    def _chunks_for(self, seconds: float) -> int:
        return math.ceil(seconds / self.chunk_seconds)

    @property
    def _oldest_sequence(self) -> int:
        return self._frames[0].sequence if self._frames else self._next_sequence
