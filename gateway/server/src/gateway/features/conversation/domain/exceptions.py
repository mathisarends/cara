from uuid import UUID


class ConversationError(Exception):
    """Base for conversation domain errors."""


class SessionNotFoundError(ConversationError):
    def __init__(self, session_id: UUID) -> None:
        super().__init__(f"Session {session_id} not found")


class ConversationInvariantError(ConversationError):
    """Base error for invalid conversation aggregate transitions."""


class PendingToolCallsError(ConversationInvariantError):
    def __init__(self) -> None:
        super().__init__("Cannot add a message while tool calls are pending")


class NoPendingToolCallSequenceError(ConversationInvariantError):
    def __init__(self) -> None:
        super().__init__("The session has no pending tool call sequence")


class DuplicateToolCallError(ConversationInvariantError):
    def __init__(self, call_id: str | None = None) -> None:
        message = "Tool call IDs must be unique within a sequence"
        if call_id is not None:
            message = f"Tool call {call_id} already exists in this sequence"
        super().__init__(message)


class ToolCallNotFoundError(ConversationInvariantError):
    def __init__(self, call_id: str) -> None:
        super().__init__(f"Tool call {call_id} not found in the pending sequence")


class ToolCallAlreadyResolvedError(ConversationInvariantError):
    def __init__(self, call_id: str) -> None:
        super().__init__(f"Tool call {call_id} has already been resolved")


class SessionBusyError(ConversationInvariantError):
    def __init__(self, session_id: UUID) -> None:
        super().__init__(f"Session {session_id} already has an active turn")


class NoActiveTurnError(ConversationInvariantError):
    def __init__(self, session_id: UUID) -> None:
        super().__init__(f"Session {session_id} has no active turn")
