import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from voice.audio.models import AudioFormat
from voice.audio.player import AudioPlayer
from voice.audio.ports import AudioOutput, AudioPlayback
from voice.backend import BackendAudio, BackendAudioEnd, BackendAudioFrame, TurnRef

_END = object()


@dataclass(frozen=True, slots=True)
class PlaybackStarted:
    """The first chunk of the turn's response reached the output."""

    turn: TurnRef


@dataclass(frozen=True, slots=True)
class PlaybackFinished:
    """The output played the turn's complete response, or failed to."""

    turn: TurnRef
    error: Exception | None = None


type PlaybackSignal = PlaybackStarted | PlaybackFinished


class PlaybackController(AudioPlayback):
    """Plays the selected turn's streamed response and clips on one output."""

    def __init__(
        self,
        output: AudioOutput,
        *,
        audio_format: AudioFormat,
        notify: Callable[[PlaybackSignal], None],
        queue_size: int = 8,
    ) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        self._player = AudioPlayer(output)
        self._format = audio_format
        self._notify = notify
        self._queue_size = queue_size
        self._selected: TurnRef | None = None
        self._response: _Response | None = None

    async def play(self, audio: bytes) -> None:
        await self._player.play(audio)

    async def select(self, turn: TurnRef) -> None:
        """Accept the response of ``turn`` and drop audio of every other turn."""
        if turn == self._selected:
            return
        # Select before awaiting, so audio accepted meanwhile is judged
        # against the new turn.
        self._selected = turn
        await self._cancel_response()

    async def release(self, turn: TurnRef) -> None:
        if turn != self._selected:
            return
        self._selected = None
        await self._cancel_response()

    async def accept(self, audio: BackendAudio) -> None:
        """Queue backend audio, waiting while the output is behind."""
        if audio.turn != self._selected:
            return
        if self._response is None:
            self._response = self._start_response(audio.turn)
        match audio:
            case BackendAudioFrame(pcm=pcm) if pcm:
                await self._response.put(pcm)
            case BackendAudioEnd():
                await self._response.put(_END)

    async def interrupt(self) -> None:
        self._selected = None
        await self._cancel_response()
        await self._player.interrupt()

    async def stop(self) -> None:
        await self.interrupt()
        await self._player.stop()

    def _start_response(self, turn: TurnRef) -> "_Response":
        queue: asyncio.Queue[bytes | object] = asyncio.Queue(self._queue_size)
        task = asyncio.create_task(
            self._play_response(turn, queue),
            name=f"voice-playback-{turn.id}",
        )
        return _Response(queue, task)

    async def _play_response(
        self, turn: TurnRef, queue: asyncio.Queue[bytes | object]
    ) -> None:
        try:
            await self._player.stream(
                _drain(queue),
                sample_rate=self._format.sample_rate,
                channels=self._format.channels,
                on_first_chunk=lambda: self._notify(PlaybackStarted(turn)),
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._notify(PlaybackFinished(turn, error))
            return
        self._notify(PlaybackFinished(turn))

    async def _cancel_response(self) -> None:
        response, self._response = self._response, None
        if response is not None:
            await response.cancel()


class _Response:
    def __init__(
        self, queue: asyncio.Queue[bytes | object], task: asyncio.Task[None]
    ) -> None:
        self._queue = queue
        self._task = task

    async def put(self, item: bytes | object) -> None:
        if self._task.done():
            return
        enqueue = asyncio.create_task(self._queue.put(item))
        try:
            await asyncio.wait(
                (enqueue, self._task), return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            if not enqueue.done():
                enqueue.cancel()
                await asyncio.gather(enqueue, return_exceptions=True)

    async def cancel(self) -> None:
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)


async def _drain(queue: asyncio.Queue[bytes | object]) -> AsyncIterator[bytes]:
    while True:
        item = await queue.get()
        if item is _END:
            return
        if isinstance(item, bytes):
            yield item
