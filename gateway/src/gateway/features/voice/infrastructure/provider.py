from collections.abc import AsyncIterator

from dishka import AsyncContainer, Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.features.conversation.application import (
    EventSource,
    SessionService,
    TurnWorker,
)
from gateway.features.voice.application import (
    AudioEncoder,
    MediaSessions,
    SpeechToText,
    TextToSpeech,
    VoiceEventPublisher,
    VoiceRecordingService,
    VoiceRecordingStore,
    VoiceSessionService,
    VoiceTurnService,
    VoiceTurnServiceConfig,
)
from gateway.features.voice.domain import VoiceSessionRepository
from gateway.features.voice.infrastructure.deepgram_stt import DeepgramSpeechToText
from gateway.features.voice.infrastructure.deepgram_tts import DeepgramTextToSpeech
from gateway.features.voice.infrastructure.lame_encoder import LameMp3Encoder
from gateway.features.voice.infrastructure.recording_store import (
    ObjectStorageVoiceRecordingStore,
)
from gateway.features.voice.infrastructure.repository import SQLVoiceSessionRepository
from gateway.features.voice.infrastructure.settings import VoiceSettings
from gateway.features.voice.presentation.media import InMemoryMediaSessions
from gateway.platform.database import ScopedUnitOfWork
from gateway.platform.storage import ObjectStorage
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
    async def deepgram_text_to_speech(
        self,
        settings: VoiceSettings,
    ) -> AsyncIterator[DeepgramTextToSpeech]:
        speech = DeepgramTextToSpeech(
            api_key=settings.deepgram_api_key.get_secret_value(),
            model=settings.tts_model,
        )
        try:
            yield speech
        finally:
            await speech.aclose()

    @provide(scope=Scope.APP)
    def text_to_speech(self, speech: DeepgramTextToSpeech) -> TextToSpeech:
        return speech

    @provide(scope=Scope.APP)
    def audio_encoder(self, settings: VoiceSettings) -> AudioEncoder:
        return LameMp3Encoder(
            output_sample_rate=24_000,
            bit_rate_kbps=settings.recording_bit_rate_kbps,
        )

    @provide(scope=Scope.APP)
    def recording_store(self, storage: ObjectStorage) -> VoiceRecordingStore:
        return ObjectStorageVoiceRecordingStore(storage)

    @provide(scope=Scope.APP)
    async def recording_service(
        self,
        sessions: VoiceSessionService,
        encoder: AudioEncoder,
        store: VoiceRecordingStore,
    ) -> AsyncIterator[VoiceRecordingService]:
        service = VoiceRecordingService(sessions, encoder, store)
        try:
            yield service
        finally:
            await service.close()

    @provide(scope=Scope.APP)
    def session_service(
        self,
        repositories: UnitOfWork[VoiceSessionRepository],
        sessions: UnitOfWork[SessionService],
        events: VoiceEventPublisher,
        media: MediaSessions,
    ) -> VoiceSessionService:
        return VoiceSessionService(repositories, sessions, events, media)

    @provide(scope=Scope.APP)
    async def turn_service(
        self,
        voice_session_unit_of_work: UnitOfWork[VoiceSessionRepository],
        voice_session_service: VoiceSessionService,
        turn_worker: TurnWorker,
        voice_event_publisher: VoiceEventPublisher,
        media_sessions: MediaSessions,
        conversation_event_source: EventSource,
        speech_to_text: SpeechToText,
        text_to_speech: TextToSpeech,
        recording_service: VoiceRecordingService,
        settings: VoiceSettings,
    ) -> AsyncIterator[VoiceTurnService]:
        config = VoiceTurnServiceConfig(
            input_queue_size=settings.input_queue_size,
            conversation_follow_up_delay_seconds=(
                settings.conversation_follow_up_delay_seconds
            ),
            conversation_inactivity_timeout_seconds=(
                settings.conversation_inactivity_timeout_seconds
            ),
            conversation_inactivity_countdown_seconds=(
                settings.conversation_inactivity_countdown_seconds
            ),
        )
        service = VoiceTurnService(
            voice_session_unit_of_work=voice_session_unit_of_work,
            voice_session_service=voice_session_service,
            turn_worker=turn_worker,
            voice_event_publisher=voice_event_publisher,
            media_sessions=media_sessions,
            conversation_event_source=conversation_event_source,
            speech_to_text=speech_to_text,
            text_to_speech=text_to_speech,
            recording_service=recording_service,
            service_config=config,
        )
        try:
            yield service
        finally:
            await service.close()
