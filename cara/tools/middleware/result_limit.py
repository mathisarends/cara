from cara.tools.middleware.base import ToolCall, ToolHandler, ToolMiddleware
from cara.tools.views import ActionResult


class ResultLimitMiddleware(ToolMiddleware):
    def __init__(self, max_chars: int = 20_000) -> None:
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        self._max_chars = max_chars

    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        result = await next(call)
        if result.ok and result.content is not None and len(result.content) > self._max_chars:
            return result.truncated(self._max_chars, note="Output truncated.")
        return result
