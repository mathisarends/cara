from cara.tools.middleware.base import ToolCall, ToolHandler, ToolMiddleware
from cara.tools.params import EditFileParams, WriteFileParams
from cara.tools.views import ActionResult


class ContentSizeMiddleware(ToolMiddleware):
    def __init__(self, max_bytes: int = 1_000_000) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._max_bytes = max_bytes

    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        content: str | None = None
        if isinstance(call.params, WriteFileParams):
            content = call.params.content
        elif isinstance(call.params, EditFileParams):
            content = call.params.new_text

        if content is not None and len(content.encode("utf-8")) > self._max_bytes:
            return ActionResult.fail(
                f"The requested file content exceeds the {self._max_bytes}-byte write limit. Write a smaller change."
            )
        return await next(call)
