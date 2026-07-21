import logging
import time

from cara.tools.middleware.base import ToolCall, ToolHandler, ToolMiddleware
from cara.tools.views import ActionResult

logger = logging.getLogger(__name__)

_BRIGHT_MAGENTA = "\x1b[95m"
_RESET = "\x1b[0m"


class CallLoggingMiddleware(ToolMiddleware):
    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        start = time.perf_counter()
        result = await next(call)
        elapsed_ms = (time.perf_counter() - start) * 1000
        status = "ok" if result.ok else "fail"
        logger.info(
            "%s[tool] %s -> %s (%.0f ms)%s",
            _BRIGHT_MAGENTA,
            call.tool.name,
            status,
            elapsed_ms,
            _RESET,
        )
        return result
