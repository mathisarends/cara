from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from collections.abc import AsyncIterator

from voice.audio.ports import AudioInput
from voice.pipeline.models import AudioFormat, AudioFrame


class AudioOverrunError(RuntimeError):
    """Raised when a consumer falls behind the bounded capture history."""


class AudioCursor:
    def __init__(self, hub: AudioHub, next_sequence: int) -> None:
        self._hub = hub
        self._next_sequence = next_sequence
        self._closed = False

    def __aiter__(self) -> AsyncIterator[AudioFrame]:
        return self

    async def __anext__(self) -> AudioFrame:
        if self._closed:
            raise StopAsyncIteration
        frame = await self._hub._read(self._next_sequence)
        if frame is None:
            self._closed = True
            raise StopAsyncIteration
        self._next_sequence += 1
        return frame

    async def aclose(self) -> None:
        self._closed = True


class AudioHub:
    """Owns one capture loop and fans frames out through independent cursors."""

    def __init__(
        self,
        input_device: AudioInput,
        *,
        frames_per_chunk: int = 1_280,
        history_seconds: float = 2.0,
        clock=time.monotonic,
    ) -> None:
        if frames_per_chunk <= 0:
            raise ValueError("frames_per_chunk must be positive")
        if history_seconds <= 0:
            raise ValueError("history_seconds must be positive")
        self._input = input_device
        self._format = AudioFormat(
            sample_rate=input_device.sample_rate,
            channels=input_device.channels,
        )
        self._chunk_frames = frames_per_chunk
        chunks_per_second = input_device.sample_rate / frames_per_chunk
        self._capacity = max(1, math.ceil(history_seconds * chunks_per_second))
        self._frames: deque[AudioFrame] = deque(maxlen=self._capacity)
        self._condition = asyncio.Condition()
        self._clock = clock
        self._next_sequence = 0
        self._capture_task: asyncio.Task[None] | None = None
        self._failure: BaseException | None = None
        self._running = False

    @property
    def format(self) -> AudioFormat:
        return self._format

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

    async def cursor(self, *, start_sequence: int | None = None) -> AudioCursor:
        async with self._condition:
            if start_sequence is None:
                start_sequence = self._next_sequence
            oldest = self._oldest_sequence
            if start_sequence < oldest:
                raise AudioOverrunError(
                    f"sequence {start_sequence} is older than retained "
                    f"sequence {oldest}"
                )
            return AudioCursor(self, start_sequence)

    async def cursor_for_detection(
        self, sequence: int, *, pre_roll_seconds: float = 0.16
    ) -> AudioCursor:
        chunks = math.ceil(
            pre_roll_seconds * self._format.sample_rate / self._chunk_frames
        )
        start = sequence - max(chunks - 1, 0)
        async with self._condition:
            return AudioCursor(self, max(start, self._oldest_sequence))

    async def _capture(self) -> None:
        try:
            async for pcm in self._input.stream_chunks():
                frame = AudioFrame(self._next_sequence, self._clock(), pcm)
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
                        f"cursor fell behind: {sequence} < retained {oldest}"
                    )
                if sequence < self._next_sequence:
                    return self._frames[sequence - oldest]
                if self._failure is not None:
                    raise self._failure
                if not self._running:
                    return None
                await self._condition.wait()

    @property
    def _oldest_sequence(self) -> int:
        return self._frames[0].sequence if self._frames else self._next_sequence
