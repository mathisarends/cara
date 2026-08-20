from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from types import MappingProxyType
from typing import Any, Literal, Protocol

from croniter import croniter

type ScheduleKind = Literal["heartbeat", "reminder", "cron"]


@dataclass(frozen=True, slots=True)
class Heartbeat:
    every: timedelta
    run_immediately: bool = True

    def __post_init__(self) -> None:
        if self.every <= timedelta(0):
            raise ValueError("Heartbeat interval must be greater than zero")


@dataclass(frozen=True, slots=True)
class Reminder:
    at: datetime

    def __post_init__(self) -> None:
        if self.at.tzinfo is None or self.at.utcoffset() is None:
            raise ValueError("Reminder time must include a timezone")


@dataclass(frozen=True, slots=True)
class Cron:
    expression: str
    timezone: tzinfo

    def __post_init__(self) -> None:
        if len(self.expression.split()) != 5 or not croniter.is_valid(self.expression):
            raise ValueError(f"Invalid five-field cron expression: {self.expression!r}")


type Trigger = Heartbeat | Reminder | Cron


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    id: str
    agent_id: str
    trigger: Trigger
    payload: Mapping[str, Any] = field(default_factory=dict)
    name: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Job id must not be empty")
        if not self.agent_id.strip():
            raise ValueError("Agent id must not be empty")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    @property
    def kind(self) -> ScheduleKind:
        match self.trigger:
            case Heartbeat():
                return "heartbeat"
            case Reminder():
                return "reminder"
            case Cron():
                return "cron"


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    job_id: str
    agent_id: str
    kind: ScheduleKind
    scheduled_for: datetime
    payload: Mapping[str, Any]
    job_name: str | None = None


class AgentRunner(Protocol):
    def __call__(self, request: AgentRunRequest) -> Awaitable[None]: ...


type ErrorHandler = Callable[[ScheduledJob, Exception], Awaitable[None]]
