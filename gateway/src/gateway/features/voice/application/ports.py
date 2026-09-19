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


class AudioEncoder(ABC):
    """Encodes mono 16-bit PCM; outputs of one encoder concatenate into one stream."""

    @abstractmethod
    async def encode(self, pcm: bytes, sample_rate: int) -> bytes: ...


class VoiceRecordingStore(ABC):
    @abstractmethod
    async def save_turn(
        self,
        voice_session_id: UUID,
        voice_turn_index: int,
        audio: bytes,
    ) -> None: ...

    @abstractmethod
    async def load(self, voice_session_id: UUID) -> bytes | None:
        """Returns the saved turns in turn order, or None if none were saved."""


class VoiceEventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: VoiceEvent) -> None: ...


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
