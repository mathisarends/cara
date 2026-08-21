from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SessionAutomationTarget:
    kind: Literal["session"]
    session_id: UUID


@dataclass(frozen=True, slots=True)
class ReminderPayload:
    kind: Literal["reminder"]
    message: str
    created_from_turn_id: UUID


@dataclass(frozen=True, slots=True)
class AutomationEnvelope:
    schema_version: Literal[1]
    target: SessionAutomationTarget
    payload: ReminderPayload
