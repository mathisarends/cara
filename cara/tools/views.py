import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from pydantic import BaseModel

from cara.tools.schemas import ToolSchema, ToolSchemaBuilder


class ActionKind(Enum):
    GENERIC = auto()
    END_SESSION = auto()


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    content: str | None = None

    @classmethod
    def success(cls, content: str | None = None) -> "ActionResult":
        return cls(ok=True, content=content)

    @classmethod
    def fail(cls, error: Exception | str) -> "ActionResult":
        return cls(ok=False, content=str(error))


type ToolCallable = Callable[..., ActionResult | Awaitable[ActionResult]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str | None
    fn: ToolCallable
    param_model: type[BaseModel] | None = None
    status_label: Callable[[Any], str] | None = None
    kind: ActionKind = ActionKind.GENERIC

    async def execute(self, kwargs: dict[str, Any]) -> ActionResult:
        result = self.fn(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result

    def to_schema(self) -> ToolSchema:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description or "",
                "parameters": ToolSchemaBuilder(self.fn, self.param_model).build(),
            },
        }
