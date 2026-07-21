import asyncio
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable

from cara.audio import AudioPlayback
from cara.speech.models import TextToSpeechFormat, TextToSpeechRequest, TextToSpeechVoice
from cara.speech.ports import TextToSpeech

logger = logging.getLogger(__name__)

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?\u2026])(?:[\"'\u00bb\u201d)\]]+)?(?=\s)")
_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n")

type _SpeechStartedHandler = Callable[[], Awaitable[None]]


class NaturalPauseChunker:
    def __init__(
        self,
        *,
        min_chunk_chars: int,
        target_chunk_chars: int,
        max_chunk_chars: int,
    ) -> None:
        if not 0 < min_chunk_chars <= target_chunk_chars <= max_chunk_chars <= 4096:
            raise ValueError("Chunk sizes must satisfy 0 < min <= target <= max <= 4096.")
        self._min_chunk_chars = min_chunk_chars
        self._target_chunk_chars = target_chunk_chars
        self._max_chunk_chars = max_chunk_chars
        self._buffer = ""

    def add(self, text: str) -> list[str]:
        self._buffer += text
        chunks: list[str] = []
        while len(self._buffer) >= self._max_chunk_chars:
            boundary = self._find_natural_boundary()
            chunk = self._buffer[:boundary].strip()
            self._buffer = self._buffer[boundary:].lstrip()
            if chunk:
                chunks.append(chunk)
                logger.info(
                    "Created natural-pause speech chunk with %d characters; %d remain buffered.",
                    len(chunk),
                    len(self._buffer),
                )
        return chunks

    def _find_natural_boundary(self) -> int:
        paragraph_boundaries = [
            match.end()
            for match in _PARAGRAPH_BOUNDARY.finditer(self._buffer, 0, self._max_chunk_chars)
            if match.end() >= self._min_chunk_chars
        ]
        if paragraph_boundaries:
            return min(
                paragraph_boundaries,
                key=lambda boundary: abs(boundary - self._target_chunk_chars),
            )

        sentence_boundaries = [
            match.end()
            for match in _SENTENCE_BOUNDARY.finditer(self._buffer, 0, self._max_chunk_chars)
            if match.end() >= self._min_chunk_chars
        ]
        if sentence_boundaries:
            return min(
                sentence_boundaries,
                key=lambda boundary: abs(boundary - self._target_chunk_chars),
            )

        word_boundary = self._buffer.rfind(" ", self._min_chunk_chars, self._max_chunk_chars + 1)
        return word_boundary + 1 if word_boundary >= 0 else self._max_chunk_chars

    def flush(self) -> str | None:
        sentence = self._buffer.strip()
        self._buffer = ""
        if sentence:
            logger.debug("Flushed final speech chunk with %d characters.", len(sentence))
        return sentence or None


class TextChunkStream(AsyncIterator[str]):
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._closed = False
        self._finished = False

    def send(self, text: str) -> None:
        if self._closed:
            raise RuntimeError("Text chunk stream is closed.")
        self._queue.put_nowait(text)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._queue.put_nowait(None)

    def __aiter__(self) -> AsyncIterator[str]:
        return self

    async def __anext__(self) -> str:
        if self._finished:
            raise StopAsyncIteration
        if (text := await self._queue.get()) is None:
            self._finished = True
            raise StopAsyncIteration
        return text


class StreamingTextToSpeech:
    def __init__(
        self,
        *,
        tts: TextToSpeech,
        player: AudioPlayback,
        voice: TextToSpeechVoice,
        instructions: str | None = None,
    ) -> None:
        self._tts = tts
        self._player = player
        self._voice = voice
        self._instructions = instructions

    async def speak(
        self,
        text_chunks: AsyncIterator[str],
        *,
        cancel: asyncio.Event | None = None,
        on_started: _SpeechStartedHandler | None = None,
    ) -> None:
        logger.info("Starting streaming text-to-speech pipeline.")
        audio_chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
        try:
            async with asyncio.TaskGroup() as task_group:
                task_group.create_task(self._synthesize(text_chunks, audio_chunks, on_started=on_started))
                task_group.create_task(self._play(audio_chunks, cancel=cancel))
        finally:
            logger.info("Streaming text-to-speech pipeline finished.")

    async def _synthesize(
        self,
        text_chunks: AsyncIterator[str],
        audio_chunks: asyncio.Queue[bytes | None],
        *,
        on_started: _SpeechStartedHandler | None,
    ) -> None:
        started = False
        chunk_number = 0
        try:
            async for text in text_chunks:
                chunk_number += 1
                if not started:
                    if on_started is not None:
                        await on_started()
                    started = True
                logger.info(
                    "Synthesizing speech chunk %d with %d characters.",
                    chunk_number,
                    len(text),
                )
                response = await self._tts.synthesize(
                    TextToSpeechRequest(
                        text=text,
                        voice=self._voice,
                        response_format=TextToSpeechFormat.WAV,
                        instructions=self._instructions,
                    )
                )
                await audio_chunks.put(response.audio)
        finally:
            audio_chunks.put_nowait(None)

    async def _play(
        self,
        audio_chunks: asyncio.Queue[bytes | None],
        *,
        cancel: asyncio.Event | None,
    ) -> None:
        chunk_number = 0
        while (audio := await audio_chunks.get()) is not None:
            if cancel is not None and cancel.is_set():
                logger.info("Streaming speech playback cancelled before the next chunk.")
                return
            chunk_number += 1
            logger.info("Playing speech chunk %d with %d bytes.", chunk_number, len(audio))
            await self._player.play(audio, cancel=cancel)
