from uuid import UUID

from gateway.features.conversation.application import SessionService
from gateway.features.voice.application.events import VoiceEvent, VoiceEventType
from gateway.features.voice.application.ports import MediaSessions, VoiceEventPublisher
from gateway.features.voice.domain import (
    AudioEncoding,
    AudioFormat,
    InvalidVoiceSessionError,
    VoiceSession,
    VoiceSessionAlreadyOpenError,
    VoiceSessionNotFoundError,
    VoiceSessionRepository,
    VoiceSessionStatus,
)
from gateway.shared import UnitOfWork

_SUPPORTED_INPUT = (AudioFormat(AudioEncoding.PCM_S16LE, 16_000, 1),)
_SUPPORTED_OUTPUT = (AudioFormat(AudioEncoding.PCM_S16LE, 24_000, 1),)


class VoiceSessionService:
    def __init__(
        self,
        repositories: UnitOfWork[VoiceSessionRepository],
        sessions: SessionService,
        events: VoiceEventPublisher,
        media: MediaSessions,
    ) -> None:
        self._repositories = repositories
        self._sessions = sessions
        self._events = events
        self._media = media

    async def open(
        self,
        session_id: UUID,
        device_id: str,
        input_formats: tuple[AudioFormat, ...],
        output_formats: tuple[AudioFormat, ...],
    ) -> VoiceSession:
        await self._sessions.get(session_id)
        input_format = _negotiate(input_formats, _SUPPORTED_INPUT, "input")
        output_format = _negotiate(output_formats, _SUPPORTED_OUTPUT, "output")
        async with self._repositories() as repository:
            existing = await repository.find_by_device(
                device_id,
                VoiceSessionStatus.OPEN,
            )
            if existing:
                raise VoiceSessionAlreadyOpenError(device_id, existing[0].id)
            voice_session = VoiceSession(
                session_id,
                device_id,
                input_format,
                output_format,
            )
            return await repository.save(voice_session)

    async def get(self, voice_session_id: UUID) -> VoiceSession:
        async with self._repositories() as repository:
            voice_session = await repository.find_by_id(voice_session_id)
        if voice_session is None:
            raise VoiceSessionNotFoundError(voice_session_id)
        return voice_session

    async def list(
        self,
        *,
        session_id: UUID | None = None,
        device_id: str | None = None,
        status: VoiceSessionStatus | None = None,
    ) -> tuple[VoiceSession, ...]:
        async with self._repositories() as repository:
            return await repository.find_many(
                session_id=session_id,
                device_id=device_id,
                status=status,
            )

    async def close(
        self,
        voice_session_id: UUID,
        reason: str = "client",
    ) -> VoiceSession:
        voice_session = await self.get(voice_session_id)
        was_open = voice_session.status is VoiceSessionStatus.OPEN
        voice_session.close(reason)
        if was_open:
            sequence = voice_session.next_sequence()
        async with self._repositories() as repository:
            voice_session = await repository.save(voice_session)
        await self._media.disconnect(voice_session_id)
        if was_open:
            await self._events.publish_voice(
                VoiceEvent(
                    VoiceEventType.SESSION_CLOSED,
                    voice_session.id,
                    voice_session.session_id,
                    {"reason": reason},
                    sequence=sequence,
                )
            )
        return voice_session

    def media_connected(self, voice_session_id: UUID) -> bool:
        return self._media.connected(voice_session_id)


def _negotiate(
    offered: tuple[AudioFormat, ...],
    supported: tuple[AudioFormat, ...],
    direction: str,
) -> AudioFormat:
    for candidate in offered:
        if candidate in supported:
            return candidate
    raise InvalidVoiceSessionError(f"No supported {direction} audio format was offered")
