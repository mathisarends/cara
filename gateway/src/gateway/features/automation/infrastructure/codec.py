from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import TypeAdapter


@dataclass(frozen=True, slots=True)
class SessionTargetRecord:
    kind: Literal["session"]
    session_id: UUID


@dataclass(frozen=True, slots=True)
class PromptActionRecord:
    kind: Literal["reminder"]
    instruction: str
    created_from_turn_id: UUID


@dataclass(frozen=True, slots=True)
class AutomationRecord:
    schema_version: Literal[2]
    target: SessionTargetRecord
    payload: PromptActionRecord


class AutomationRecordCodec:
    def __init__(self) -> None:
        self._adapter = TypeAdapter(AutomationRecord)

    def encode(self, value: AutomationRecord) -> str:
        return self._adapter.dump_json(value).decode()

    def decode(self, value: str) -> AutomationRecord:
        return self._adapter.validate_json(value)
