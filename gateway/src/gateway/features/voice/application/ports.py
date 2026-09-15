from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator
from uuid import UUID

from gateway.features.voice.application.events import VoiceEvent


class Transcription:
    def __init__(self, text: str, is_final: bool) -> None:
        self._text = text
        self._is_final = is_final

    @property
    def text(self) -> str:
        return self._text

    @property
    def is_final(self) -> bool:
        return self._is_final


class SpeechToText(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio: AsyncIterable[bytes],
    ) -> AsyncIterator[Transcription]: ...


class TextToSpeech(ABC):
    @abstractmethod
    def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]: ...


class VoiceEventPublisher(ABC):
    @abstractmethod
    async def publish_voice(self, event: VoiceEvent) -> None: ...


class MediaSessions(ABC):
    @abstractmethod
    def connected(self, voice_session_id: UUID) -> bool: ...

    @abstractmethod
    async def disconnect(self, voice_session_id: UUID) -> None: ...

    @abstractmethod
    async def send_audio(
        self,
        voice_session_id: UUID,
        voice_turn_index: int,
        sequence: int,
        timestamp_ms: int,
        payload: bytes,
        *,
        end: bool = False,
    ) -> None: ...
