from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from gateway.features.conversation.domain import (
    RunNotFoundError,
    SessionNotFoundError,
)


@dataclass(frozen=True, slots=True)
class CommandRejection:
    code: str
    message: str


_HTTP_HANDLERS: tuple[tuple[type[Exception], int, str], ...] = (
    (SessionNotFoundError, 404, "Session not found"),
    (RunNotFoundError, 404, "Run not found in this session"),
)


def command_rejection(
    error: ValidationError | SessionNotFoundError | RunNotFoundError,
) -> CommandRejection:
    if isinstance(error, ValidationError):
        return CommandRejection("invalid_command", str(error))
    if isinstance(error, SessionNotFoundError):
        return CommandRejection("session_not_found", "Session not found")
    return CommandRejection("run_not_found", "Run not found in this session")


def _make_handler(status_code: int, default_detail: str):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=status_code,
            content={"detail": str(exc) or default_detail},
        )

    return handler


def register_exception_handlers(app: FastAPI) -> None:
    for exception, status_code, detail in _HTTP_HANDLERS:
        app.add_exception_handler(exception, _make_handler(status_code, detail))
