from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import TypeAdapter

from gateway.features.automation.domain import AutomationTarget, SessionTarget


@dataclass(frozen=True, slots=True)
class SessionTargetRecord:
    kind: Literal["session"]
    session_id: UUID


type AutomationTargetRecord = SessionTargetRecord


@dataclass(frozen=True, slots=True)
class PromptActionRecord:
    kind: Literal["reminder"]
    instruction: str
    created_from_turn_id: UUID


@dataclass(frozen=True, slots=True)
class AutomationRecord:
    schema_version: Literal[3]
    owner_id: str
    target: AutomationTargetRecord
    payload: PromptActionRecord


class AutomationRecordCodec:
    def __init__(self) -> None:
        self._adapter = TypeAdapter(AutomationRecord)

    def encode(self, value: AutomationRecord) -> str:
        return self._adapter.dump_json(value).decode()

    def decode(self, value: str) -> AutomationRecord:
        return self._adapter.validate_json(value)


def automation_target(record: AutomationTargetRecord) -> AutomationTarget:
    match record:
        case SessionTargetRecord(session_id=session_id):
            return SessionTarget(session_id)


def target_record(target: AutomationTarget) -> AutomationTargetRecord:
    match target:
        case SessionTarget(session_id=session_id):
            return SessionTargetRecord(kind="session", session_id=session_id)
