from datetime import UTC, datetime
from uuid import UUID

from gateway.features.voice.domain.errors import InvalidVoiceTurnTransitionError
from gateway.features.voice.domain.values import Activation, VoiceTurnStatus
from gateway.shared import Entity


class VoiceTurn(Entity):
    def __init__(
        self,
        index: int,
        activation: Activation,
        status: VoiceTurnStatus = VoiceTurnStatus.LISTENING,
        *,
        id: UUID | None = None,
        created_at: datetime | None = None,
        transcript: str | None = None,
        user_message_id: UUID | None = None,
        stt_provider: str | None = None,
        tts_provider: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        input_ended_at: datetime | None = None,
        transcribed_at: datetime | None = None,
        speech_started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        if index < 1:
            raise ValueError("Voice turn index must be positive")
        super().__init__(id=id, created_at=created_at)
        self._index = index
        self._activation = activation
        self._status = status
        self._transcript = transcript
        self._user_message_id = user_message_id
        self._stt_provider = stt_provider
        self._tts_provider = tts_provider
        self._error_code = error_code
        self._error_message = error_message
        self._input_ended_at = input_ended_at
        self._transcribed_at = transcribed_at
        self._speech_started_at = speech_started_at
        self._ended_at = ended_at

    @classmethod
    def proactive(cls, index: int) -> "VoiceTurn":
        return cls(
            index,
            Activation.PROACTIVE,
            VoiceTurnStatus.WAITING_FOR_ASSISTANT,
        )

    @property
    def index(self) -> int:
        return self._index

    @property
    def activation(self) -> Activation:
        return self._activation

    @property
    def status(self) -> VoiceTurnStatus:
        return self._status

    @property
    def transcript(self) -> str | None:
        return self._transcript

    @property
    def user_message_id(self) -> UUID | None:
        return self._user_message_id

    @property
    def stt_provider(self) -> str | None:
        return self._stt_provider

    @property
    def tts_provider(self) -> str | None:
        return self._tts_provider

    @property
    def error_code(self) -> str | None:
        return self._error_code

    @property
    def error_message(self) -> str | None:
        return self._error_message

    @property
    def input_ended_at(self) -> datetime | None:
        return self._input_ended_at

    @property
    def transcribed_at(self) -> datetime | None:
        return self._transcribed_at

    @property
    def speech_started_at(self) -> datetime | None:
        return self._speech_started_at

    @property
    def ended_at(self) -> datetime | None:
        return self._ended_at

    def end_input(self, now: datetime | None = None) -> None:
        self._transition(VoiceTurnStatus.TRANSCRIBING, VoiceTurnStatus.LISTENING)
        self._input_ended_at = now or datetime.now(UTC)

    def transcribe(
        self,
        transcript: str,
        user_message_id: UUID,
        now: datetime | None = None,
    ) -> None:
        normalized = " ".join(transcript.split())
        if not normalized:
            raise ValueError("A final transcript must contain text")
        self._transition(
            VoiceTurnStatus.WAITING_FOR_ASSISTANT,
            VoiceTurnStatus.LISTENING,
            VoiceTurnStatus.TRANSCRIBING,
        )
        self._transcript = normalized
        self._user_message_id = user_message_id
        self._transcribed_at = now or datetime.now(UTC)

    def discard(self, now: datetime | None = None) -> None:
        self._transition(
            VoiceTurnStatus.DISCARDED,
            VoiceTurnStatus.LISTENING,
            VoiceTurnStatus.TRANSCRIBING,
        )
        self._ended_at = now or datetime.now(UTC)

    def start_speaking(self, now: datetime | None = None) -> None:
        self._transition(
            VoiceTurnStatus.SPEAKING,
            VoiceTurnStatus.WAITING_FOR_ASSISTANT,
        )
        self._speech_started_at = now or datetime.now(UTC)

    def complete(self, now: datetime | None = None) -> None:
        self._transition(VoiceTurnStatus.COMPLETED, VoiceTurnStatus.SPEAKING)
        self._ended_at = now or datetime.now(UTC)

    def cancel(self, now: datetime | None = None) -> None:
        self._require_active()
        self._status = VoiceTurnStatus.CANCELLED
        self._ended_at = now or datetime.now(UTC)

    def fail(
        self,
        code: str,
        message: str,
        now: datetime | None = None,
    ) -> None:
        self._require_active()
        self._status = VoiceTurnStatus.FAILED
        self._error_code = code
        self._error_message = message
        self._ended_at = now or datetime.now(UTC)

    def _require_active(self) -> None:
        if self.status.terminal:
            raise InvalidVoiceTurnTransitionError(
                f"Voice turn {self.id} is already {self.status}"
            )

    def _transition(
        self,
        target: VoiceTurnStatus,
        *allowed: VoiceTurnStatus,
    ) -> None:
        if self.status not in allowed:
            raise InvalidVoiceTurnTransitionError(
                f"Cannot move voice turn {self.id} from {self.status} to {target}"
            )
        self._status = target
