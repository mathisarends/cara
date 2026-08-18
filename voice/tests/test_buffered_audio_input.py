import asyncio
from collections.abc import AsyncIterator

import pytest

from voice.audio import AudioInput, AudioOverrunError, BufferedAudioInput


class _ControlledInput(AudioInput):
    def __init__(self) -> None:
        self._active = False
        self._chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self.opens = 0

    @property
    def sample_rate(self) -> int:
        return 16_000

    @property
    def channels(self) -> int:
        return 1

    @property
    def frames_per_chunk(self) -> int:
        return 1280

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self) -> None:
        self.opens += 1
        self._active = True

    async def stop(self) -> None:
        self._active = False

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        while self._active:
            yield await self._chunks.get()

    async def send(self, value: int) -> None:
        await self._chunks.put(bytes([value]))


async def _wait_until_captured() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)


def test_exposes_input_audio_format() -> None:
    buffered_input = BufferedAudioInput(_ControlledInput())

    assert buffered_input.sample_rate == 16_000
    assert buffered_input.channels == 1


def test_detection_cursor_includes_pre_roll_without_reopening_input() -> None:
    async def run() -> tuple[list[int], int]:
        input_device = _ControlledInput()
        buffered_input = BufferedAudioInput(input_device)
        await buffered_input.start()
        for value in range(4):
            await input_device.send(value)
        await _wait_until_captured()

        cursor = await buffered_input.cursor(from_sequence=3, pre_roll_seconds=0.16)
        frames = [await anext(cursor), await anext(cursor)]
        second_cursor = await buffered_input.cursor()
        await buffered_input.stop()
        await second_cursor.aclose()
        return [frame.sequence for frame in frames], input_device.opens

    sequences, opens = asyncio.run(run())

    assert sequences == [2, 3]
    assert opens == 1


def test_slow_cursor_fails_explicitly_after_ring_buffer_overrun() -> None:
    async def run() -> None:
        input_device = _ControlledInput()
        buffered_input = BufferedAudioInput(input_device, history_seconds=0.16)
        await buffered_input.start()
        cursor = await buffered_input.cursor(from_sequence=0)
        for value in range(4):
            await input_device.send(value)
        await _wait_until_captured()

        with pytest.raises(AudioOverrunError):
            await anext(cursor)
        await buffered_input.stop()

    asyncio.run(run())
