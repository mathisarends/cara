from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Self
from uuid import UUID

from gateway.features.conversation.domain.entities import (
    AssistantMessage,
    SessionEntry,
    ToolCall,
    ToolCallSequence,
    UserMessage,
)
from gateway.features.conversation.domain.exceptions import (
    NoPendingToolCallSequenceError,
    PendingToolCallsError,
)
from gateway.features.conversation.domain.models import ChannelRef
from gateway.shared import Aggregate


class Session(Aggregate):
    def __init__(
        self,
        channel: ChannelRef,
        metadata: Mapping[str, Any] | None = None,
        entries: Sequence[SessionEntry] = (),
        turn_active: bool = False,
        *,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at)
        self._channel = channel
        self._metadata = dict(metadata or {})
        self._entries = list(entries)
        self._turn_active = turn_active

    @classmethod
    def create(
        cls,
        channel: ChannelRef,
        metadata: Mapping[str, Any] | None = None,
    ) -> Self:
        return cls(channel=channel, metadata=metadata)

    @property
    def channel(self) -> ChannelRef:
        return self._channel

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    @property
    def entries(self) -> tuple[SessionEntry, ...]:
        return tuple(self._entries)

    @property
    def turn_active(self) -> bool:
        return self._turn_active

    def add_user_message(self, content: str) -> UserMessage:
        if self._find_pending_tool_call_sequence() is not None:
            raise PendingToolCallsError()
        message = UserMessage(content)
        self._entries.append(message)
        return message

    def add_assistant_message(self, content: str) -> AssistantMessage:
        if self._find_pending_tool_call_sequence() is not None:
            raise PendingToolCallsError()
        message = AssistantMessage(content)
        self._entries.append(message)
        return message

    def add_tool_call(
        self,
        call_id: str,
        function_name: str,
        function_arguments: Mapping[str, Any],
    ) -> ToolCall:
        call = ToolCall(call_id, function_name, function_arguments)
        sequence = self._current_tool_call_sequence()
        if sequence is None:
            sequence = ToolCallSequence()
            self._entries.append(sequence)
        sequence.add(call)
        return call

    def resolve_tool_call(self, call_id: str, result: Any) -> ToolCall:
        return self._require_pending_tool_call_sequence().resolve(call_id, result)

    def fail_tool_call(self, call_id: str, error: str) -> ToolCall:
        return self._require_pending_tool_call_sequence().fail(call_id, error)

    def fail_pending_tool_calls(self, error: str) -> tuple[ToolCall, ...]:
        sequence = self._find_pending_tool_call_sequence()
        if sequence is None:
            return ()
        failed_calls: list[ToolCall] = []
        for call in sequence.calls:
            if call.is_pending:
                call.fail(error)
                failed_calls.append(call)
        return tuple(failed_calls)

    def pending_tool_call_sequence(self) -> ToolCallSequence | None:
        return self._find_pending_tool_call_sequence()

    def _current_tool_call_sequence(self) -> ToolCallSequence | None:
        if not self._entries:
            return None
        entry = self._entries[-1]
        if isinstance(entry, ToolCallSequence) and not entry.is_complete:
            return entry
        return None

    def _find_pending_tool_call_sequence(self) -> ToolCallSequence | None:
        for entry in reversed(self._entries):
            if isinstance(entry, ToolCallSequence) and not entry.is_complete:
                return entry
        return None

    def _require_pending_tool_call_sequence(self) -> ToolCallSequence:
        sequence = self._find_pending_tool_call_sequence()
        if sequence is None:
            raise NoPendingToolCallSequenceError()
        return sequence
