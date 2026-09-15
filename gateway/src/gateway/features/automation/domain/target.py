from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Literal
from uuid import UUID


class TargetKind(StrEnum):
    SESSION = "session"
    CHANNEL = "channel"


@dataclass(frozen=True, slots=True)
class SessionTarget:
    kind: ClassVar[Literal[TargetKind.SESSION]] = TargetKind.SESSION
    session_id: UUID


@dataclass(frozen=True, slots=True)
class ChannelTarget:
    kind: ClassVar[Literal[TargetKind.CHANNEL]] = TargetKind.CHANNEL
    channel: str

    def __post_init__(self) -> None:
        if not self.channel.strip():
            raise ValueError("Automation target channel must not be empty")


type AutomationTarget = SessionTarget | ChannelTarget
