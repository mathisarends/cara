import asyncio
import logging
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from vocalbin.deepgram.tts import TextToSpeech as _VocalbinTextToSpeech
from vocalbin.deepgram.tts import TextToSpeechModel as DeepgramVoice
from websockets.exceptions import ConnectionClosed

from voice.tts.port import TextToSpeech

_DEFAULT_VOICE = DeepgramVoice.AURA_2_THALIA_EN
_DEFAULT_SAMPLE_RATE = 24_000
_DEFAULT_SEGMENT_IDLE_SECONDS = 0.5
_DEFAULT_RECONNECT_ATTEMPTS = 1

logger = logging.getLogger(__name__)


class DeepgramTextToSpeech(_VocalbinTextToSpeech, TextToSpeech):
    """Adapts Deepgram's incremental WebSocket stream to the TTS port."""

    def __init__(
        self,
        *,
        voice: DeepgramVoice | str = _DEFAULT_VOICE,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        segment_idle_seconds: float = _DEFAULT_SEGMENT_IDLE_SECONDS,
        reconnect_attempts: int = _DEFAULT_RECONNECT_ATTEMPTS,
        **kwargs: Any,
    ) -> None:
        if segment_idle_seconds <= 0:
            raise ValueError("segment_idle_seconds must be positive")
        if reconnect_attempts < 0:
            raise ValueError("reconnect_attempts must not be negative")
        super().__init__(model=voice, sample_rate=sample_rate, **kwargs)
        self._sample_rate = sample_rate
        self._segment_idle_seconds = segment_idle_seconds
        self._reconnect_attempts = reconnect_attempts

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    async def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]:
        async for segment in _text_segments(text, self._segment_idle_seconds):
            async for chunk in self._synthesize_segment(segment):
                yield chunk

    async def _synthesize_segment(
        self, segment: tuple[str, ...]
    ) -> AsyncIterator[bytes]:
        for attempt in range(self._reconnect_attempts + 1):
            emitted_audio = False
            try:
                async for chunk in self.stream_incremental(_stream_segment(segment)):
                    emitted_audio = True
                    yield chunk
                return
            except ConnectionClosed:
                if emitted_audio or attempt == self._reconnect_attempts:
                    raise
                logger.warning(
                    "Deepgram TTS connection closed before audio arrived; "
                    "reconnecting (%d/%d)",
                    attempt + 1,
                    self._reconnect_attempts,
                )


async def _text_segments(
    text: AsyncIterable[str], idle_seconds: float
) -> AsyncIterator[tuple[str, ...]]:
    queue: asyncio.Queue[str | Exception | None] = asyncio.Queue()
    producer = asyncio.create_task(
        _produce_text(text, queue),
        name="deepgram-tts-text-producer",
    )
    try:
        while True:
            item = await queue.get()
            if item is None:
                return
            if isinstance(item, Exception):
                raise item

            segment = [item]
            while True:
                try:
                    async with asyncio.timeout(idle_seconds):
                        item = await queue.get()
                except TimeoutError:
                    break
                if item is None:
                    yield tuple(segment)
                    return
                if isinstance(item, Exception):
                    raise item
                segment.append(item)

            yield tuple(segment)
    finally:
        if not producer.done():
            producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)


async def _produce_text(
    text: AsyncIterable[str],
    queue: asyncio.Queue[str | Exception | None],
) -> None:
    try:
        async for chunk in text:
            if chunk:
                queue.put_nowait(chunk)
    except Exception as error:
        queue.put_nowait(error)
    finally:
        queue.put_nowait(None)


async def _stream_segment(segment: tuple[str, ...]) -> AsyncIterator[str]:
    for chunk in segment:
        yield chunk
