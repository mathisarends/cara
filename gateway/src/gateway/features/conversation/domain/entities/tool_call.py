from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from gateway.features.conversation.domain.exceptions import (
    ToolCallAlreadyResolvedError,
)
from gateway.shared import Entity


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
