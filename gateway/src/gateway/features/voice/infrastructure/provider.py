from collections.abc import AsyncIterator

from dishka import AsyncContainer, Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.features.conversation.application import (
    EventSource,
    SessionService,
    TurnService,
)
from gateway.features.voice.application import (
    MediaSessions,
    SpeechToText,
    TextToSpeech,
    VoiceEventPublisher,
    VoiceSessionService,
    VoiceTurnService,
)
from gateway.features.voice.domain import VoiceSessionRepository
from gateway.features.voice.infrastructure.deepgram_stt import DeepgramSpeechToText
from gateway.features.voice.infrastructure.deepgram_tts import DeepgramTextToSpeech
from gateway.features.voice.infrastructure.repository import SQLVoiceSessionRepository
from gateway.features.voice.infrastructure.settings import VoiceSettings
from gateway.features.voice.presentation.media import InMemoryMediaSessions
from gateway.platform.database import ScopedUnitOfWork
from gateway.shared import UnitOfWork


class VoiceProvider(Provider):
    @provide(scope=Scope.APP)
    def settings(self) -> VoiceSettings:
        return VoiceSettings()

    @provide(scope=Scope.REQUEST)
    def repository(self, session: AsyncSession) -> VoiceSessionRepository:
        return SQLVoiceSessionRepository(session)

    @provide(scope=Scope.APP)
    def repository_unit_of_work(
        self,
        container: AsyncContainer,
    ) -> UnitOfWork[VoiceSessionRepository]:
        return ScopedUnitOfWork(container, VoiceSessionRepository)

    @provide(scope=Scope.APP)
    def media_sessions(self) -> InMemoryMediaSessions:
        return InMemoryMediaSessions()

    @provide(scope=Scope.APP)
    def media_sessions_port(self, media: InMemoryMediaSessions) -> MediaSessions:
        return media

    @provide(scope=Scope.APP)
    def speech_to_text(self, settings: VoiceSettings) -> SpeechToText:
        return DeepgramSpeechToText(
            api_key=settings.deepgram_api_key.get_secret_value(),
            model=settings.stt_model,
        )

    @provide(scope=Scope.APP)
    def text_to_speech(self, settings: VoiceSettings) -> TextToSpeech:
        return DeepgramTextToSpeech(
            api_key=settings.deepgram_api_key.get_secret_value(),
            model=settings.tts_model,
        )

    @provide(scope=Scope.APP)
    def session_service(
        self,
        repositories: UnitOfWork[VoiceSessionRepository],
        sessions: SessionService,
        events: VoiceEventPublisher,
        media: MediaSessions,
    ) -> VoiceSessionService:
        return VoiceSessionService(repositories, sessions, events, media)

    @provide(scope=Scope.APP)
    async def turn_service(
        self,
        repositories: UnitOfWork[VoiceSessionRepository],
        sessions: VoiceSessionService,
        turns: TurnService,
        events: VoiceEventPublisher,
        media: MediaSessions,
        conversation_events: EventSource,
        speech_to_text: SpeechToText,
        text_to_speech: TextToSpeech,
        settings: VoiceSettings,
    ) -> AsyncIterator[VoiceTurnService]:
        service = VoiceTurnService(
            repositories,
            sessions,
            turns,
            events,
            media,
            conversation_events,
            speech_to_text,
            text_to_speech,
            settings.input_queue_size,
            settings.conversation_inactivity_timeout_seconds,
            settings.conversation_inactivity_countdown_seconds,
        )
        try:
            yield service
        finally:
            await service.close()
