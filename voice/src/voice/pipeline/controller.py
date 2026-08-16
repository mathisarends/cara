import asyncio
import contextlib
import re
from collections.abc import AsyncIterator

from agent.events import (
    AssistantSpeechStarted,
    AssistantTurnStarted,
    UserSpeechEnded,
    UserSpeechStarted,
    UserTurnStarted,
)
from voice.audio.hub import AudioCursor, AudioHub
from voice.audio.playback_coordinator import PlaybackCoordinator
from voice.events import (
    AssistantAudioChunk,
    AssistantAudioCompleted,
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantTextCompleted,
    UserTranscriptionUpdated,
    VoiceTurnFailed,
    VoiceTurnTimedOut,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded, VoiceTurnRequested
from voice.llm import ChatModel
from voice.stt import SpeechToText, Transcription
from voice.tts import TextToSpeech

_END = object()


class _ProducerFailure:
    def __init__(self, error: BaseException) -> None:
        self.error = error


class TurnController:
    """Coordinates one cancellable voice turn while capture stays alive."""

    def __init__(
        self,
        *,
        audio_hub: AudioHub,
        wake_word_phrase: str,
        speech_to_text: SpeechToText,
        llm: ChatModel,
        text_to_speech: TextToSpeech,
        playback: PlaybackCoordinator,
        event_bus: EventBus,
        command_pre_roll_seconds: float = 0.16,
        speech_start_timeout: float = 8.0,
        tts_sample_rate: int = 24_000,
        text_queue_size: int = 8,
    ) -> None:
        if speech_start_timeout <= 0:
            raise ValueError("speech_start_timeout must be positive")
        if text_queue_size <= 0:
            raise ValueError("text_queue_size must be positive")
        self._audio_hub = audio_hub
        self._stt = speech_to_text
        self._llm = llm
        self._tts = text_to_speech
        self._playback = playback
        self._event_bus = event_bus
        self._wake_word_phrase = wake_word_phrase
        self._pre_roll = command_pre_roll_seconds
        self._speech_start_timeout = speech_start_timeout
        self._tts_sample_rate = tts_sample_rate
        self._text_queue_size = text_queue_size
        self._next_turn_id = 0
        self._active_turn_id: int | None = None
        self._active_task: asyncio.Task[None] | None = None
        self._closed = False

        event_bus.on(VoiceTurnRequested, self._on_turn_requested)

    @property
    def has_active_turn(self) -> bool:
        return self._active_task is not None and not self._active_task.done()

    async def close(self) -> None:
        self._closed = True
        await self.interrupt()

    async def interrupt(self) -> bool:
        task = self._active_task
        if task is None or task.done():
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def _on_turn_requested(self, event: VoiceTurnRequested) -> None:
        if self._closed:
            return
        if self.has_active_turn:
            raise RuntimeError("Cannot start a voice turn while another is active.")
        cursor = await self._cursor_for(event)
        self._next_turn_id += 1
        turn_id = self._next_turn_id
        self._active_turn_id = turn_id
        await self._event_bus.dispatch(UserTurnStarted())
        if self._closed:
            self._active_turn_id = None
            await cursor.aclose()
            await self._event_bus.dispatch(VoiceTurnEnded(turn_id=turn_id))
            return
        self._active_task = asyncio.create_task(
            self._run_turn(
                turn_id,
                cursor,
                event.speech_start_timeout or self._speech_start_timeout,
            ),
            name=f"voice-turn-{turn_id}",
        )

    async def _run_turn(
        self, turn_id: int, cursor: AudioCursor, speech_start_timeout: float
    ) -> None:
        transcriptions: AsyncIterator | None = None
        try:
            transcriptions = self._stt.transcribe(_pcm_chunks(cursor))
            try:
                first = await asyncio.wait_for(
                    anext(transcriptions), timeout=speech_start_timeout
                )
            except TimeoutError:
                await self._event_bus.dispatch(VoiceTurnTimedOut(turn_id=turn_id))
                return

            await self._dispatch_transcription(turn_id, first)
            await self._event_bus.dispatch(UserSpeechStarted())
            final_text = first.text if first.is_final else None
            while final_text is None:
                update = await anext(transcriptions)
                await self._dispatch_transcription(turn_id, update)
                if update.is_final:
                    final_text = update.text

            await self._event_bus.dispatch(UserSpeechEnded())
            if not self._is_current(turn_id):
                return
            text = _strip_known_wake_word(final_text, self._wake_word_phrase)
            await self._event_bus.dispatch(AssistantTurnStarted())
            await self._respond(turn_id, text)
        except asyncio.CancelledError:
            raise
        except StopAsyncIteration:
            pass
        except Exception as error:
            await self._event_bus.dispatch(
                VoiceTurnFailed(turn_id=turn_id, message=str(error))
            )
        finally:
            if transcriptions is not None:
                await transcriptions.aclose()
            await cursor.aclose()
            if self._is_current(turn_id):
                self._active_turn_id = None
                self._active_task = None
                await self._event_bus.dispatch(VoiceTurnEnded(turn_id=turn_id))

    async def _respond(self, turn_id: int, text: str) -> None:
        await self._event_bus.dispatch(AssistantResponseStarted(turn_id=turn_id))
        queue: asyncio.Queue[str | object | _ProducerFailure] = asyncio.Queue(
            self._text_queue_size
        )
        producer = asyncio.create_task(
            _produce_text(
                self._llm.respond(text),
                queue,
                event_bus=self._event_bus,
                turn_id=turn_id,
            ),
            name=f"voice-llm-{turn_id}",
        )

        def speech_started() -> None:
            if not self._is_current(turn_id):
                return
            asyncio.ensure_future(self._event_bus.dispatch(AssistantSpeechStarted()))

        pcm = self._tts.synthesize(_consume_text(queue))
        try:
            await self._playback.stream(
                _publish_audio(pcm, self._event_bus, turn_id),
                sample_rate=self._tts_sample_rate,
                is_current=lambda: self._is_current(turn_id),
                on_first_chunk=speech_started,
            )
            if self._is_current(turn_id):
                await self._event_bus.dispatch(AssistantTextCompleted(turn_id=turn_id))
                await self._event_bus.dispatch(AssistantAudioCompleted(turn_id=turn_id))
        finally:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
            with contextlib.suppress(Exception):
                await pcm.aclose()

    async def _dispatch_transcription(
        self, turn_id: int, update: Transcription
    ) -> None:
        await self._event_bus.dispatch(
            UserTranscriptionUpdated(
                turn_id=turn_id,
                text=update.text,
                is_final=update.is_final,
                kind=update.kind,
            )
        )

    async def _cursor_for(self, event: VoiceTurnRequested) -> AudioCursor:
        if event.sequence is None:
            return await self._audio_hub.cursor()
        return await self._audio_hub.cursor_for_detection(
            event.sequence, pre_roll_seconds=self._pre_roll
        )

    def _is_current(self, turn_id: int) -> bool:
        return self._active_turn_id == turn_id


async def _pcm_chunks(cursor: AudioCursor) -> AsyncIterator[bytes]:
    async for frame in cursor:
        yield frame.pcm


async def _produce_text(
    chunks: AsyncIterator[str],
    queue: asyncio.Queue[str | object | _ProducerFailure],
    *,
    event_bus: EventBus,
    turn_id: int,
) -> None:
    try:
        async for chunk in chunks:
            if chunk:
                await event_bus.dispatch(
                    AssistantTextChunk(turn_id=turn_id, chunk=chunk)
                )
                await queue.put(chunk)
    except asyncio.CancelledError:
        raise
    except BaseException as error:
        await queue.put(_ProducerFailure(error))
        await queue.put(_END)
    else:
        await queue.put(_END)
    finally:
        await chunks.aclose()


async def _consume_text(
    queue: asyncio.Queue[str | object | _ProducerFailure],
) -> AsyncIterator[str]:
    while True:
        item = await queue.get()
        if item is _END:
            return
        if isinstance(item, _ProducerFailure):
            raise item.error
        if isinstance(item, str):
            yield item


async def _publish_audio(
    chunks: AsyncIterator[bytes], event_bus: EventBus, turn_id: int
) -> AsyncIterator[bytes]:
    async for chunk in chunks:
        if chunk:
            await event_bus.dispatch(AssistantAudioChunk(turn_id=turn_id, chunk=chunk))
            yield chunk


def _strip_known_wake_word(text: str, phrase: str) -> str:
    if not phrase:
        return text.strip()
    pattern = rf"^\s*{re.escape(phrase)}(?=\s|[,.:;!?-]|$)[\s,.:;!?-]*"
    return re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip()
