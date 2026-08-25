from datetime import datetime
from typing import Any
from uuid import UUID

from gateway.features.conversation.domain.entities.tool_call import ToolCall
from gateway.features.conversation.domain.exceptions import (
    DuplicateToolCallError,
    ToolCallNotFoundError,
)
from gateway.shared import Entity


class ToolCallSequence(Entity):
    def __init__(
        self,
        calls: list[ToolCall] | None = None,
        *,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at)
        self._calls = list(calls or [])
        call_ids = [call.call_id for call in self._calls]
        if len(call_ids) != len(set(call_ids)):
            raise DuplicateToolCallError()

    @property
    def calls(self) -> tuple[ToolCall, ...]:
        return tuple(self._calls)

    @property
    def is_complete(self) -> bool:
        return all(not call.is_pending for call in self._calls)

    def add(self, call: ToolCall) -> None:
        if any(existing.call_id == call.call_id for existing in self._calls):
            raise DuplicateToolCallError(call.call_id)
        self._calls.append(call)

    def resolve(self, call_id: str, result: Any) -> ToolCall:
        call = self._require_call(call_id)
        call.complete(result)
        return call

    def fail(self, call_id: str, error: str) -> ToolCall:
        call = self._require_call(call_id)
        call.fail(error)
        return call

    def _require_call(self, call_id: str) -> ToolCall:
        for call in self._calls:
            if call.call_id == call_id:
                return call
        raise ToolCallNotFoundError(call_id)
