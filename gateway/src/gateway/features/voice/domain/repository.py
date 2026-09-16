from abc import ABC, abstractmethod
from uuid import UUID

from gateway.features.voice.domain.values import VoiceSessionStatus
from gateway.features.voice.domain.voice_session import VoiceSession


class VoiceSessionRepository(ABC):
    @abstractmethod
    async def find_by_id(self, id: UUID) -> VoiceSession | None: ...

    @abstractmethod
    async def find_by_room(
        self,
        room: str,
        status: VoiceSessionStatus | None = None,
    ) -> tuple[VoiceSession, ...]: ...

    @abstractmethod
    async def find_many(
        self,
        *,
        session_id: UUID | None = None,
        room: str | None = None,
        status: VoiceSessionStatus | None = None,
    ) -> tuple[VoiceSession, ...]: ...

    @abstractmethod
    async def save(self, domain: VoiceSession) -> VoiceSession: ...
