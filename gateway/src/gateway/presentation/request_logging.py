import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    """Logs HTTP requests and WebSocket connections, including their duration.

    Implemented as raw ASGI rather than `BaseHTTPMiddleware` so that WebSocket
    connections are covered too; the event stream is where turns stall.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        match scope["type"]:
            case "http":
                await self._call_http(scope, receive, send)
            case "websocket":
                await self._call_websocket(scope, receive, send)
            case _:
                await self._app(scope, receive, send)

    async def _call_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        target = _target(scope)
        method = scope["method"]
        logger.info("--> %s %s", method, target)
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        except Exception:
            logger.exception(
                "<-- %s %s raised after %s", method, target, _elapsed(started)
            )
            raise
        logger.info("<-- %s %s %s %s", method, target, status, _elapsed(started))

    async def _call_websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        target = _target(scope)
        logger.info("--> WS %s connecting", target)
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            match message["type"]:
                case "websocket.accept":
                    logger.info("=== WS %s accepted", target)
                case "websocket.send":
                    logger.debug("<<< WS %s frame", target)
                case "websocket.close":
                    logger.info(
                        "<-- WS %s closed (code %s) after %s",
                        target,
                        message.get("code", 1000),
                        _elapsed(started),
                    )
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("<-- WS %s raised after %s", target, _elapsed(started))
            raise

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._app!r})"


def _target(scope: Scope) -> str:
    path = scope["path"]
    query = scope.get("query_string", b"").decode()
    return f"{path}?{query}" if query else path


def _elapsed(started: float) -> str:
    return f"{(time.perf_counter() - started) * 1000:.1f}ms"
