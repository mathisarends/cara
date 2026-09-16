import asyncio
from contextlib import asynccontextmanager
from typing import cast

from gateway.features.conversation.application import EventSource, TurnService
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
        device_id="kitchen",
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
        0.02,
        0,
    )

    try:
        first_turn = await service.start(voice_session.id, Activation.WAKE_WORD)
        first_turn.end_input()
        first_turn.transcribe("hello", _uuid())
        first_turn.start_speaking()

        await service.playback_completed(first_turn.id)
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


class _VoiceEvents:
    def __init__(self) -> None:
        self.items = []

    async def publish_voice(self, event) -> None:
        self.items.append(event)


class _MediaSessions:
    def connected(self, _voice_session_id) -> bool:
        return True


class _EmptySpeechToText:
    async def transcribe(self, audio):
        yield Transcription("", False)
        async for _ in audio:
            pass
        yield Transcription("", True)
