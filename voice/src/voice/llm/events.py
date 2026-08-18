from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class TurnCompleted:
    pass


@dataclass(frozen=True, slots=True)
class ToolStarted:
    name: str


@dataclass(frozen=True, slots=True)
class ToolCompleted:
    name: str


type AgentEvent = TextDelta | TurnCompleted | ToolStarted | ToolCompleted
