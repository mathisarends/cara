import asyncio
from collections.abc import AsyncIterable, Callable

from voice.audio.ports import AudioOutput


class StreamingAudioPlayer:
    """Writes raw PCM as it arrives instead of buffering a complete response."""

    def __init__(self, output: AudioOutput) -> None:
        self._output = output

    async def play(
        self,
        chunks: AsyncIterable[bytes],
        *,
        sample_rate: int,
        channels: int = 1,
        is_current: Callable[[], bool] | None = None,
        on_first_chunk: Callable[[], None] | None = None,
    ) -> None:
        await self._output.start(sample_rate=sample_rate, channels=channels)
        first = True
        try:
            async for chunk in chunks:
                if not chunk:
                    continue
                if is_current is not None and not is_current():
                    await self._output.clear_buffer()
                    return
                if first:
                    first = False
                    if on_first_chunk is not None:
                        on_first_chunk()
                await self._output.play_chunk(chunk)
            if is_current is None or is_current():
                await self._output.finish_response()
        except asyncio.CancelledError:
            await asyncio.shield(self._output.clear_buffer())
            raise
