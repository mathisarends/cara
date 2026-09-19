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
        sessions: UnitOfWork[SessionService],
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
        room: str,
        input_formats: tuple[AudioFormat, ...],
        output_formats: tuple[AudioFormat, ...],
    ) -> VoiceSession:
        async with self._sessions() as sessions:
            await sessions.get(session_id)
        input_format = _negotiate(input_formats, _SUPPORTED_INPUT, "input")
        output_format = _negotiate(output_formats, _SUPPORTED_OUTPUT, "output")
        async with self._repositories() as repository:
            existing = await repository.find_by_room(
                room,
                VoiceSessionStatus.OPEN,
            )
            if existing:
                raise VoiceSessionAlreadyOpenError(room, existing[0].id)
            voice_session = VoiceSession(
                session_id,
                room,
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
        room: str | None = None,
        status: VoiceSessionStatus | None = None,
    ) -> tuple[VoiceSession, ...]:
        async with self._repositories() as repository:
            return await repository.find_many(
                session_id=session_id,
                room=room,
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
            await self._events.publish(
                VoiceEvent(
                    VoiceEventType.SESSION_CLOSED,
                    voice_session.id,
                    voice_session.session_id,
                    {"reason": reason},
                    sequence=sequence,
                )
            )
        return voice_session

    async def switch_to_new_conversation(self, voice_session: VoiceSession) -> None:
        """Point the voice session at a fresh conversation session; the caller saves."""
        async with self._sessions() as sessions:
            current = await sessions.get(voice_session.session_id)
            conversation = await sessions.create(channel=current.channel)
        voice_session.switch_conversation(conversation.id)

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
