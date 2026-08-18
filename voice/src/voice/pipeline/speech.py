import asyncio
import contextlib
import logging
import re
from collections.abc import AsyncIterator

from voice.audio.hub import AudioCursor
from voice.events import (
    AssistantAudioChunk,
    AssistantAudioCompleted,
    AssistantAudioStarted,
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantTextCompleted,
    AssistantTurnStarted,
    UserAudioChunk,
    UserSpeechEnded,
    UserSpeechStarted,
    UserTranscriptionUpdated,
    VoiceTurnTimedOut,
)
from voice.events.bus import EventBus
from voice.llm import AgentEvent, AgentSession, TextDelta, TurnCompleted
from voice.stt import SpeechToText, Transcription
from voice.tts import TextToSpeech

logger = logging.getLogger(__name__)

_END = object()


class _ProducerFailure:
    def __init__(self, error: BaseException) -> None:
        self.error = error


class SpeechPipeline:
    """Transforms one captured utterance into event-published response audio."""

    def __init__(
        self,
        *,
        wake_word_phrase: str,
        speech_to_text: SpeechToText,
        agent_session: AgentSession,
        text_to_speech: TextToSpeech,
        event_bus: EventBus,
        tts_sample_rate: int = 24_000,
        text_queue_size: int = 8,
    ) -> None:
        if tts_sample_rate <= 0:
            raise ValueError("tts_sample_rate must be positive")
        if text_queue_size <= 0:
            raise ValueError("text_queue_size must be positive")
        self._wake_word_phrase = wake_word_phrase
        self._stt = speech_to_text
        self._agent_session = agent_session
        self._tts = text_to_speech
        self._event_bus = event_bus
        self._tts_sample_rate = tts_sample_rate
        self._text_queue_size = text_queue_size

    async def run(
        self,
        *,
        turn_id: int,
        audio: AudioCursor,
        speech_start_timeout: float,
    ) -> None:
        transcriptions = self._stt.transcribe(
            _publish_user_audio(audio, self._event_bus, turn_id)
        )
        try:
            try:
                first = await asyncio.wait_for(
                    anext(transcriptions), timeout=speech_start_timeout
                )
            except TimeoutError:
                logger.debug(
                    "Turn %d: no speech within %.1fs, timing out",
                    turn_id,
                    speech_start_timeout,
                )
                await self._event_bus.dispatch(VoiceTurnTimedOut(turn_id=turn_id))
                return
            except StopAsyncIteration:
                return

            await self._publish_transcription(turn_id, first)
            await self._event_bus.dispatch(UserSpeechStarted())
            final_text = first.text if first.is_final else None
            while final_text is None:
                update = await anext(transcriptions)
                await self._publish_transcription(turn_id, update)
                if update.is_final:
                    final_text = update.text

            await self._event_bus.dispatch(UserSpeechEnded())
            text = _strip_known_wake_word(final_text, self._wake_word_phrase)
            logger.debug("Turn %d: user said %r", turn_id, text)
            await self._event_bus.dispatch(AssistantTurnStarted())
            await self._respond(turn_id, text)
        finally:
            await transcriptions.aclose()

    async def _respond(self, turn_id: int, text: str) -> None:
        await self._event_bus.dispatch(AssistantResponseStarted(turn_id=turn_id))
        queue: asyncio.Queue[str | object | _ProducerFailure] = asyncio.Queue(
            self._text_queue_size
        )
        producer: asyncio.Task[str] | None = None
        pcm: AsyncIterator[bytes] | None = None
        try:
            events = await self._agent_session.start_turn(text)
            producer = asyncio.create_task(
                _produce_text(
                    events,
                    queue,
                    event_bus=self._event_bus,
                    turn_id=turn_id,
                ),
                name=f"voice-agent-{turn_id}",
            )
            pcm = self._tts.synthesize(_consume_text(queue))
            await self._event_bus.dispatch(
                AssistantAudioStarted(
                    turn_id=turn_id,
                    sample_rate=self._tts_sample_rate,
                )
            )
            async for chunk in pcm:
                if chunk:
                    await self._event_bus.dispatch(
                        AssistantAudioChunk(turn_id=turn_id, chunk=chunk)
                    )
            transcript = await producer
            await self._event_bus.dispatch(
                AssistantTextCompleted(turn_id=turn_id, text=transcript)
            )
            await self._event_bus.dispatch(AssistantAudioCompleted(turn_id=turn_id))
        except asyncio.CancelledError:
            await self._agent_session.interrupt()
            raise
        finally:
            if producer is not None:
                producer.cancel()
                await asyncio.gather(producer, return_exceptions=True)
            if pcm is not None:
                with contextlib.suppress(Exception):
                    await pcm.aclose()

    async def _publish_transcription(self, turn_id: int, update: Transcription) -> None:
        await self._event_bus.dispatch(
            UserTranscriptionUpdated(
                turn_id=turn_id,
                text=update.text,
                is_final=update.is_final,
                kind=update.kind,
            )
        )


async def _publish_user_audio(
    cursor: AudioCursor, event_bus: EventBus, turn_id: int
) -> AsyncIterator[bytes]:
    async for frame in cursor:
        await event_bus.dispatch(UserAudioChunk(turn_id=turn_id, chunk=frame.pcm))
        yield frame.pcm


async def _produce_text(
    events: AsyncIterator[AgentEvent],
    queue: asyncio.Queue[str | object | _ProducerFailure],
    *,
    event_bus: EventBus,
    turn_id: int,
) -> str:
    chunks: list[str] = []
    try:
        async for event in events:
            if isinstance(event, TextDelta) and event.text:
                chunks.append(event.text)
                await event_bus.dispatch(
                    AssistantTextChunk(turn_id=turn_id, chunk=event.text)
                )
                await queue.put(event.text)
            elif isinstance(event, TurnCompleted):
                break
    except asyncio.CancelledError:
        raise
    except BaseException as error:
        await queue.put(_ProducerFailure(error))
        await queue.put(_END)
    else:
        await queue.put(_END)
    return "".join(chunks)


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
