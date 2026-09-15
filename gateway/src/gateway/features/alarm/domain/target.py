from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Literal
from uuid import UUID


class TargetKind(StrEnum):
    SESSION = "session"


@dataclass(frozen=True, slots=True)
class SessionTarget:
    kind: ClassVar[Literal[TargetKind.SESSION]] = TargetKind.SESSION
    session_id: UUID


type AlarmTarget = SessionTarget
