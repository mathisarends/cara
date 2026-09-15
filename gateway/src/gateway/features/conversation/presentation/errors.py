from fastapi_canon import Error, ErrorRegistry

from gateway.features.conversation.domain import SessionNotFoundError

SESSION_NOT_FOUND = Error(
    SessionNotFoundError,
    status=404,
    code="session_not_found",
    title="Session not found",
    detail=str,
)

CONVERSATION_ERRORS = ErrorRegistry(
    name="conversation",
    errors=[SESSION_NOT_FOUND],
)
