class ConversationError(Exception):
    """Base for conversation domain errors."""


class SessionNotFoundError(ConversationError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session {session_id} not found")


class RunNotFoundError(ConversationError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run {run_id} not found in this session")
