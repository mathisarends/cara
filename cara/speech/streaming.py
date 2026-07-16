import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable

from cara.audio import AudioPlayer
from cara.speech.models import TextToSpeechFormat, TextToSpeechRequest, TextToSpeechVoice
from cara.speech.ports import TextToSpeech

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?\u2026])(?:[\"'\u00bb\u201d)\]]+)?(?=\s)")

type _SpeechStartedHandler = Callable[[], Awaitable[None]]


class PunctuationSentenceChunker:
    def __init__(self) -> None:
        self._buffer = ""

    def add(self, text: str) -> list[str]:
        self._buffer += text
        sentences: list[str] = []
        start = 0
        for match in _SENTENCE_BOUNDARY.finditer(self._buffer):
            if sentence := self._buffer[start : match.end()].strip():
                sentences.append(sentence)
            start = match.end()
        self._buffer = self._buffer[start:]
        return sentences

    def flush(self) -> str | None:
        sentence = self._buffer.strip()
        self._buffer = ""
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
        player: AudioPlayer,
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
        audio_chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
        async with asyncio.TaskGroup() as task_group:
            task_group.create_task(self._synthesize(text_chunks, audio_chunks, on_started=on_started))
            task_group.create_task(self._play(audio_chunks, cancel=cancel))

    async def _synthesize(
        self,
        text_chunks: AsyncIterator[str],
        audio_chunks: asyncio.Queue[bytes | None],
        *,
        on_started: _SpeechStartedHandler | None,
    ) -> None:
        started = False
        try:
            async for text in text_chunks:
                if not started:
                    if on_started is not None:
                        await on_started()
                    started = True
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
        while (audio := await audio_chunks.get()) is not None:
            if cancel is not None and cancel.is_set():
                return
            await self._player.play(audio, cancel=cancel)
