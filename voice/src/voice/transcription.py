from dataclasses import dataclass
from enum import StrEnum


class TranscriptionKind(StrEnum):
    START = "start"
    UPDATE = "update"
    EAGER_END = "eager_end"
    RESUME = "resume"
    END = "end"


@dataclass(frozen=True)
class Transcription:
    text: str
    is_final: bool
    kind: TranscriptionKind = TranscriptionKind.UPDATE
