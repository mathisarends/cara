from fastapi_canon import Error, ErrorRegistry

from gateway.features.conversation.domain import (
    NoActiveTurnError,
    SessionBusyError,
    SessionNotFoundError,
)

SESSION_NOT_FOUND = Error(
    SessionNotFoundError,
    status=404,
    code="session_not_found",
    title="Session not found",
    detail=str,
)

TURN_ALREADY_RUNNING = Error(
    SessionBusyError,
    status=409,
    code="turn_already_running",
    title="Turn already running",
    detail=str,
)

NO_ACTIVE_TURN = Error(
    NoActiveTurnError,
    status=409,
    code="no_active_turn",
    title="No active turn",
    detail=str,
)

CONVERSATION_ERRORS = ErrorRegistry(
    name="conversation",
    errors=[SESSION_NOT_FOUND, TURN_ALREADY_RUNNING, NO_ACTIVE_TURN],
)
