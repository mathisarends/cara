from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gateway.features.conversation.domain import (
    NoActiveTurnError,
    SessionBusyError,
    SessionNotFoundError,
)

_HTTP_HANDLERS: tuple[tuple[type[Exception], int, str], ...] = (
    (SessionNotFoundError, 404, "Session not found"),
    (NoActiveTurnError, 409, "Session has no active turn"),
    (SessionBusyError, 409, "Session already has an active turn"),
)


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
