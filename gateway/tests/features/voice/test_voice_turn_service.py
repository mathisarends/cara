import asyncio
import time
from contextlib import asynccontextmanager
from typing import cast

from gateway.features.conversation.application import (
    ConversationEvent,
    ConversationEventType,
    EventSource,
    TurnService,
)
from gateway.features.conversation.domain import ChannelRef
from gateway.features.voice.application import (
    MediaSessions,
    SpeechToText,
    TextToSpeech,
    Transcription,
    VoiceEventPublisher,
    VoiceEventType,
)
from gateway.features.voice.application.voice_session_service import VoiceSessionService
from gateway.features.voice.application.voice_turn_service import VoiceTurnService
from gateway.features.voice.domain import (
    Activation,
    AudioEncoding,
    AudioFormat,
    VoiceSession,
    VoiceSessionRepository,
    VoiceTurnStatus,
)
from gateway.shared import UnitOfWork


async def test_gateway_owns_follow_up_and_ends_inactive_conversation() -> None:
    voice_session = VoiceSession(
        session_id=_uuid(),
        room="kitchen",
        input_format=AudioFormat(AudioEncoding.PCM_S16LE, 16_000, 1),
        output_format=AudioFormat(AudioEncoding.PCM_S16LE, 24_000, 1),
    )
    repository = _VoiceSessionRepository(voice_session)
    events = _VoiceEvents()
    service = VoiceTurnService(
        cast(UnitOfWork[VoiceSessionRepository], _UnitOfWork(repository)),
        cast(VoiceSessionService, _VoiceSessions(voice_session)),
        cast(TurnService, object()),
        cast(VoiceEventPublisher, events),
        cast(MediaSessions, _MediaSessions()),
        cast(EventSource, object()),
        cast(SpeechToText, _EmptySpeechToText()),
        cast(TextToSpeech, object()),
        8,
        0.01,
        0.02,
        0,
    )

    try:
        first_turn = await service.start(voice_session.id, Activation.WAKE_WORD)
        first_turn.end_input()
        first_turn.transcribe("hello", _uuid())
        first_turn.start_speaking()

        started_at = time.monotonic()
        await service.playback_completed(first_turn.id)
        assert time.monotonic() - started_at >= 0.01
        await asyncio.sleep(0.05)

        lifecycle = [
            event.type
            for event in events.items
            if event.type is not VoiceEventType.TRANSCRIPT_PARTIAL
        ]
        assert lifecycle == [
            VoiceEventType.CONVERSATION_STARTED,
            VoiceEventType.TURN_STARTED,
            VoiceEventType.TURN_COMPLETED,
            VoiceEventType.TURN_STARTED,
            VoiceEventType.TURN_DISCARDED,
            VoiceEventType.CONVERSATION_ENDED,
        ]
        follow_up = voice_session.turns[-1]
        assert follow_up.activation is Activation.FOLLOW_UP
        assert follow_up.status is VoiceTurnStatus.DISCARDED
        assert events.items[-1].data == {"reason": "inactivity_timeout"}
    finally:
        await service.close()


async def test_wake_word_without_speech_ends_inactive_conversation() -> None:
    voice_session = VoiceSession(
        session_id=_uuid(),
        room="bedroom",
        input_format=AudioFormat(AudioEncoding.PCM_S16LE, 16_000, 1),
        output_format=AudioFormat(AudioEncoding.PCM_S16LE, 24_000, 1),
    )
    repository = _VoiceSessionRepository(voice_session)
    events = _VoiceEvents()
    service = VoiceTurnService(
        cast(UnitOfWork[VoiceSessionRepository], _UnitOfWork(repository)),
        cast(VoiceSessionService, _VoiceSessions(voice_session)),
        cast(TurnService, object()),
        cast(VoiceEventPublisher, events),
        cast(MediaSessions, _MediaSessions()),
        cast(EventSource, object()),
        cast(SpeechToText, _EmptySpeechToText()),
        cast(TextToSpeech, object()),
        8,
        0,
        0.02,
        0,
    )

    try:
        turn = await service.start(voice_session.id, Activation.WAKE_WORD)
        await asyncio.sleep(0.05)

        assert turn.status is VoiceTurnStatus.DISCARDED
        assert events.items[-1].type is VoiceEventType.CONVERSATION_ENDED
        assert events.items[-1].data == {"reason": "inactivity_timeout"}
    finally:
        await service.close()


async def test_ended_conversation_moves_the_next_wake_word_to_a_new_session() -> None:
    voice_session = VoiceSession(
        session_id=_uuid(),
        room="bedroom",
        input_format=AudioFormat(AudioEncoding.PCM_S16LE, 16_000, 1),
        output_format=AudioFormat(AudioEncoding.PCM_S16LE, 24_000, 1),
    )
    ended_session_id = voice_session.session_id
    repository = _VoiceSessionRepository(voice_session)
    events = _VoiceEvents()
    service = VoiceTurnService(
        cast(UnitOfWork[VoiceSessionRepository], _UnitOfWork(repository)),
        cast(VoiceSessionService, _VoiceSessions(voice_session)),
        cast(TurnService, object()),
        cast(VoiceEventPublisher, events),
        cast(MediaSessions, _MediaSessions()),
        cast(EventSource, object()),
        cast(SpeechToText, _EmptySpeechToText()),
        cast(TextToSpeech, object()),
        8,
        0,
        0.02,
        0,
    )

    try:
        await service.start(voice_session.id, Activation.WAKE_WORD)
        await asyncio.sleep(0.05)
        await service.start(voice_session.id, Activation.WAKE_WORD)

        lifecycle = [
            event
            for event in events.items
            if event.type is not VoiceEventType.TRANSCRIPT_PARTIAL
        ]
        ended, started = lifecycle[-3], lifecycle[-2]
        assert ended.type is VoiceEventType.CONVERSATION_ENDED
        assert ended.session_id == ended_session_id
        assert started.type is VoiceEventType.CONVERSATION_STARTED
        assert started.session_id == voice_session.session_id != ended_session_id
    finally:
        await service.close()


async def test_proactive_turn_streams_a_scheduled_answer_to_the_room() -> None:
    voice_session = VoiceSession(
        session_id=_uuid(),
        room="bedroom",
        input_format=AudioFormat(AudioEncoding.PCM_S16LE, 16_000, 1),
        output_format=AudioFormat(AudioEncoding.PCM_S16LE, 24_000, 1),
    )
    repository = _VoiceSessionRepository(voice_session)
    events = _VoiceEvents()
    conversation_events = _ConversationEvents(voice_session.session_id)
    media = _MediaSessions()
    text_to_speech = _TextToSpeech()
    turns = _ScheduledTurns(conversation_events, text_to_speech)
    service = VoiceTurnService(
        cast(UnitOfWork[VoiceSessionRepository], _UnitOfWork(repository)),
        cast(VoiceSessionService, _VoiceSessions(voice_session)),
        cast(TurnService, turns),
        cast(VoiceEventPublisher, events),
        cast(MediaSessions, media),
        cast(EventSource, conversation_events),
        cast(SpeechToText, _EmptySpeechToText()),
        cast(TextToSpeech, text_to_speech),
        8,
        0,
        30,
        5,
    )

    try:
        turn = await service.start_proactive(
            voice_session.id,
            text="scheduled prompt",
        )

        assert turn.activation is Activation.PROACTIVE
        assert turn.status is VoiceTurnStatus.SPEAKING
        assert text_to_speech.segments == [
            "Let me check.",
            "Your train ticket reminder",
        ]
        assert [frame[-1] for frame in media.frames] == [False, False, True]
        assert [event.type for event in events.items] == [
            VoiceEventType.CONVERSATION_STARTED,
            VoiceEventType.TURN_STARTED,
            VoiceEventType.ASSISTANT_TEXT_STARTED,
            VoiceEventType.ASSISTANT_TOOL_STARTED,
            VoiceEventType.ASSISTANT_AUDIO_STARTED,
            VoiceEventType.ASSISTANT_TOOL_COMPLETED,
            VoiceEventType.ASSISTANT_AUDIO_COMPLETED,
        ]
        assert events.items[3].data == {"name": "list_reminders"}
    finally:
        await service.close()


def _uuid():
    from uuid import uuid4

    return uuid4()


class _UnitOfWork:
    def __init__(self, repository: "_VoiceSessionRepository") -> None:
        self._repository = repository

    @asynccontextmanager
    async def __call__(self):
        yield self._repository


class _VoiceSessionRepository:
    def __init__(self, voice_session: VoiceSession) -> None:
        self._voice_session = voice_session

    async def save(self, voice_session: VoiceSession) -> VoiceSession:
        self._voice_session = voice_session
        return voice_session

    async def find_many(self, **_):
        return (self._voice_session,)


class _VoiceSessions:
    def __init__(self, voice_session: VoiceSession) -> None:
        self._voice_session = voice_session

    async def get(self, voice_session_id):
        assert voice_session_id == self._voice_session.id
        return self._voice_session

    async def switch_to_new_conversation(self, voice_session: VoiceSession) -> None:
        voice_session.switch_conversation(_uuid())


class _VoiceEvents:
    def __init__(self) -> None:
        self.items = []

    async def publish_voice(self, event) -> None:
        self.items.append(event)


class _MediaSessions:
    def __init__(self) -> None:
        self.frames: list[tuple[object, ...]] = []

    def connected(self, _voice_session_id) -> bool:
        return True

    async def send_audio(self, *values, end: bool = False) -> None:
        self.frames.append((*values, end))


class _EmptySpeechToText:
    async def transcribe(self, audio):
        yield Transcription("", False)
        async for _ in audio:
            pass
        yield Transcription("", True)


class _ConversationSubscription:
    def __init__(self, queue: asyncio.Queue[ConversationEvent]) -> None:
        self._queue = queue

    async def receive(self) -> ConversationEvent:
        return await self._queue.get()


class _ConversationEvents:
    def __init__(self, session_id) -> None:
        self._session_id = session_id
        self._queue: asyncio.Queue[ConversationEvent] = asyncio.Queue()

    @asynccontextmanager
    async def listen(self, session_id):
        assert session_id == self._session_id
        yield _ConversationSubscription(self._queue)

    async def publish(self, event_type: ConversationEventType, data: dict) -> None:
        await self._queue.put(
            ConversationEvent(
                type=event_type,
                session_id=self._session_id,
                channel=ChannelRef("voice"),
                data=data,
            )
        )


class _ScheduledTurns:
    def __init__(
        self, events: _ConversationEvents, text_to_speech: "_TextToSpeech"
    ) -> None:
        self._events = events
        self._text_to_speech = text_to_speech

    async def start_scheduled(
        self,
        *,
        session_id,
        text: str,
    ) -> None:
        assert text == "scheduled prompt"
        await self._events.publish(
            ConversationEventType.CHAT_DELTA,
            {"text": "Let me check."},
        )
        await self._events.publish(
            ConversationEventType.TOOL_CALL_STARTED,
            {"name": "list_reminders", "arguments": {}},
        )
        await asyncio.wait_for(self._text_to_speech.first_segment_spoken.wait(), 1)
        await self._events.publish(
            ConversationEventType.TOOL_CALL_COMPLETED,
            {"name": "list_reminders", "result": "[]", "is_error": False},
        )
        await self._events.publish(
            ConversationEventType.CHAT_DELTA,
            {"text": "Your train ticket reminder"},
        )
        await self._events.publish(ConversationEventType.CHAT_COMPLETED, {})
        await self._events.publish(ConversationEventType.TURN_COMPLETED, {})


class _TextToSpeech:
    def __init__(self) -> None:
        self.segments: list[str] = []
        self.first_segment_spoken = asyncio.Event()

    async def synthesize(self, text):
        self.segments.append("".join([chunk async for chunk in text]))
        yield b"audio"
        self.first_segment_spoken.set()
