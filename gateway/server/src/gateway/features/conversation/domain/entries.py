from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from gateway.features.conversation.domain.exceptions import (
    DuplicateToolCallError,
    ToolCallAlreadyResolvedError,
    ToolCallNotFoundError,
)
from gateway.shared import Entity


class UserMessage(Entity):
    def __init__(
        self,
        content: str,
        *,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at)
        self._content = content

    @property
    def content(self) -> str:
        return self._content


class AssistantMessage(Entity):
    def __init__(
        self,
        content: str,
        *,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at)
        self._content = content

    @property
    def content(self) -> str:
        return self._content


class ToolCallState(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolCall(Entity):
    def __init__(
        self,
        call_id: str,
        function_name: str,
        function_arguments: Mapping[str, Any],
        *,
        state: ToolCallState = ToolCallState.PENDING,
        result: Any = None,
        error: str | None = None,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at)
        self._call_id = call_id
        self._function_name = function_name
        self._function_arguments = dict(function_arguments)
        self._state = state
        self._result = result
        self._error = error

    @property
    def call_id(self) -> str:
        return self._call_id

    @property
    def function_name(self) -> str:
        return self._function_name

    @property
    def function_arguments(self) -> dict[str, Any]:
        return dict(self._function_arguments)

    @property
    def state(self) -> ToolCallState:
        return self._state

    @property
    def result(self) -> Any:
        return self._result

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def is_pending(self) -> bool:
        return self._state is ToolCallState.PENDING

    def complete(self, result: Any) -> None:
        self._assert_pending()
        self._result = result
        self._state = ToolCallState.COMPLETED

    def fail(self, error: str) -> None:
        self._assert_pending()
        self._error = error
        self._state = ToolCallState.FAILED

    def _assert_pending(self) -> None:
        if not self.is_pending:
            raise ToolCallAlreadyResolvedError(self._call_id)


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


type SessionEntry = UserMessage | AssistantMessage | ToolCallSequence
