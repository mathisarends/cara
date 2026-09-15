from enum import StrEnum


class AudioEncoding(StrEnum):
    PCM_S16LE = "pcm_s16le"


class VoiceSessionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Activation(StrEnum):
    WAKE_WORD = "wake_word"
    MANUAL = "manual"
    FOLLOW_UP = "follow_up"
    BARGE_IN = "barge_in"
    PROACTIVE = "proactive"


class VoiceTurnStatus(StrEnum):
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    WAITING_FOR_ASSISTANT = "waiting_for_assistant"
    SPEAKING = "speaking"
    COMPLETED = "completed"
    DISCARDED = "discarded"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in {
            VoiceTurnStatus.COMPLETED,
            VoiceTurnStatus.DISCARDED,
            VoiceTurnStatus.CANCELLED,
            VoiceTurnStatus.FAILED,
        }


class AudioFormat:
    def __init__(
        self,
        encoding: AudioEncoding,
        sample_rate: int,
        channels: int,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("Audio sample rate must be positive")
        if channels != 1:
            raise ValueError("Only mono audio is currently supported")
        self._encoding = encoding
        self._sample_rate = sample_rate
        self._channels = channels

    @property
    def encoding(self) -> AudioEncoding:
        return self._encoding

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, AudioFormat)
            and self.encoding == other.encoding
            and self.sample_rate == other.sample_rate
            and self.channels == other.channels
        )
