import asyncio
import contextlib
import re
from collections.abc import AsyncIterator

from transitbus import EventBus

from agent.events import (
    AssistantInterrupted,
    AssistantSpeechStarted,
    AssistantTurnStarted,
    UserSpeechEnded,
    UserSpeechStarted,
    UserTurnStarted,
)
from voice.audio.hub import AudioCursor, AudioHub
from voice.audio.playback_coordinator import PlaybackCoordinator
from voice.events import VoiceTurnFailed, VoiceTurnTimedOut, WakeWordDetected
from voice.llm import ChatModel
from voice.pipeline.models import TurnState
from voice.stt import SpeechToText
from voice.tts import TextToSpeech
from voice.wakeword import WakeWordDetection, WakeWordSource

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
        wake_word: WakeWordSource,
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
        self._wake_word = wake_word
        self._stt = speech_to_text
        self._llm = llm
        self._tts = text_to_speech
        self._playback = playback
        self._event_bus = event_bus
        self._wake_word_phrase = wake_word.phrase
        self._pre_roll = command_pre_roll_seconds
        self._speech_start_timeout = speech_start_timeout
        self._tts_sample_rate = tts_sample_rate
        self._text_queue_size = text_queue_size
        self._state = TurnState.STARTING
        self._next_turn_id = 0
        self._active_turn_id: int | None = None
        self._active_task: asyncio.Task[None] | None = None

    @property
    def state(self) -> TurnState:
        return self._state

    @property
    def active_turn_id(self) -> int | None:
        return self._active_turn_id

    async def run(self) -> None:
        await self._audio_hub.start()
        self._state = TurnState.ARMED
        try:
            async for detection in self._wake_word.detections():
                await self._handle_detection(detection)
        finally:
            await self.close()

    async def close(self) -> None:
        task, self._active_task = self._active_task, None
        self._active_turn_id = None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._playback.interrupt()
        await self._audio_hub.stop()

    async def _handle_detection(self, detection: WakeWordDetection) -> None:
        if self._state is TurnState.LISTENING:
            return

        cursor = await self._audio_hub.cursor_for_detection(
            detection.sequence, pre_roll_seconds=self._pre_roll
        )
        previous = self._active_task
        if previous is not None and not previous.done():
            await self._playback.interrupt()
            previous.cancel()
            await asyncio.gather(previous, return_exceptions=True)
            await self._event_bus.dispatch(AssistantInterrupted())

        self._next_turn_id += 1
        turn_id = self._next_turn_id
        self._active_turn_id = turn_id
        self._state = TurnState.LISTENING
        self._active_task = asyncio.create_task(
            self._run_turn(turn_id, cursor), name=f"voice-turn-{turn_id}"
        )
        await self._event_bus.dispatch(
            WakeWordDetected(
                score=detection.score,
                sequence=detection.sequence,
                name=detection.name,
            )
        )

    async def _run_turn(self, turn_id: int, cursor: AudioCursor) -> None:
        transcriptions: AsyncIterator | None = None
        try:
            await self._event_bus.dispatch(UserTurnStarted())
            transcriptions = self._stt.transcribe(_pcm_chunks(cursor))
            try:
                first = await asyncio.wait_for(
                    anext(transcriptions), timeout=self._speech_start_timeout
                )
            except TimeoutError:
                await self._event_bus.dispatch(VoiceTurnTimedOut(turn_id=turn_id))
                return

            await self._event_bus.dispatch(UserSpeechStarted())
            final_text = first.text if first.is_final else None
            while final_text is None:
                update = await anext(transcriptions)
                if update.is_final:
                    final_text = update.text

            await self._event_bus.dispatch(UserSpeechEnded())
            if not self._is_current(turn_id):
                return
            text = _strip_known_wake_word(final_text, self._wake_word_phrase)
            self._state = TurnState.THINKING
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
                self._state = TurnState.ARMED

    async def _respond(self, turn_id: int, text: str) -> None:
        queue: asyncio.Queue[str | object | _ProducerFailure] = asyncio.Queue(
            self._text_queue_size
        )
        producer = asyncio.create_task(
            _produce_text(self._llm.respond(text), queue),
            name=f"voice-llm-{turn_id}",
        )

        def speech_started() -> None:
            if not self._is_current(turn_id):
                return
            self._state = TurnState.SPEAKING
            asyncio.ensure_future(self._event_bus.dispatch(AssistantSpeechStarted()))

        try:
            pcm = self._tts.synthesize(_consume_text(queue))
            await self._playback.stream(
                pcm,
                sample_rate=self._tts_sample_rate,
                is_current=lambda: self._is_current(turn_id),
                on_first_chunk=speech_started,
            )
        finally:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
            with contextlib.suppress(Exception):
                await pcm.aclose()

    def _is_current(self, turn_id: int) -> bool:
        return self._active_turn_id == turn_id


async def _pcm_chunks(cursor: AudioCursor) -> AsyncIterator[bytes]:
    async for frame in cursor:
        yield frame.pcm


async def _produce_text(
    chunks: AsyncIterator[str], queue: asyncio.Queue[str | object | _ProducerFailure]
) -> None:
    try:
        async for chunk in chunks:
            if chunk:
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


def _strip_known_wake_word(text: str, phrase: str) -> str:
    if not phrase:
        return text.strip()
    pattern = rf"^\s*{re.escape(phrase)}(?=\s|[,.:;!?-]|$)[\s,.:;!?-]*"
    return re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip()
