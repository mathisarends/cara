import asyncio
from collections.abc import AsyncIterator

from voice.audio import AudioOutput, AudioPlayer


class _RecordingOutput(AudioOutput):
    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.finished = False

    @property
    def is_playing(self) -> bool:
        return bool(self.chunks) and not self.finished

    async def start(self, *, sample_rate: int, channels: int) -> None:
        assert (sample_rate, channels) == (24_000, 1)

    async def stop(self) -> None:
        pass

    async def play_chunk(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def finish_response(self) -> None:
        self.finished = True

    async def clear_buffer(self) -> None:
        self.chunks.clear()


def test_first_pcm_chunk_is_played_before_synthesis_finishes() -> None:
    async def run() -> tuple[_RecordingOutput, bool]:
        output = _RecordingOutput()
        release = asyncio.Event()

        async def chunks() -> AsyncIterator[bytes]:
            yield b"first"
            await release.wait()
            yield b"second"

        task = asyncio.create_task(
            AudioPlayer(output).stream(chunks(), sample_rate=24_000)
        )
        while not output.chunks:
            await asyncio.sleep(0)
        was_running = not task.done()
        release.set()
        await task
        return output, was_running

    output, was_running = asyncio.run(run())

    assert was_running
    assert output.chunks == [b"first", b"second"]
    assert output.finished
