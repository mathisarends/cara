from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any

from cara.tools.di import ToolContext
from cara.tools.params import ToolParams
from cara.tools.views import ActionResult, Tool


@dataclass(frozen=True)
class ToolCall:
    tool: Tool
    params: ToolParams | None
    raw_args: dict[str, Any]
    context: ToolContext


type ToolHandler = Callable[[ToolCall], Awaitable[ActionResult]]


class ToolMiddleware(ABC):
    @abstractmethod
    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        """Handle a tool call or delegate it to the next middleware."""


def compose(middlewares: Sequence[ToolMiddleware], terminal: ToolHandler) -> ToolHandler:
    handler = terminal
    for middleware in reversed(middlewares):
        handler = partial(middleware, next=handler)
    return handler
