import asyncio
from collections.abc import AsyncIterable, Callable

from voice.audio.output.player import AudioPlayer
from voice.audio.ports import AudioOutput
from voice.audio.streaming_player import StreamingAudioPlayer


class PlaybackCoordinator:
    """Serializes WAV earcons and streaming speech on one physical output."""

    def __init__(self, output: AudioOutput) -> None:
        self._output = output
        self._wav_player = AudioPlayer(output)
        self._streaming_player = StreamingAudioPlayer(output)
        self._lock = asyncio.Lock()

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        async with self._lock:
            await self._wav_player.play(audio, cancel=cancel)

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
            await self._streaming_player.play(
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
