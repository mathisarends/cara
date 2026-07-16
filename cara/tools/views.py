import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Self

from pydantic import ValidationError

from cara.tools.params import ToolParams
from cara.tools.schemas import ToolSchema, ToolSchemaBuilder


class ActionKind(Enum):
    GENERIC = auto()
    END_SESSION = auto()


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    content: str | None = None

    @classmethod
    def success(cls, content: str | None = None) -> Self:
        return cls(ok=True, content=content)

    @classmethod
    def fail(cls, error: Exception | str) -> Self:
        return cls(ok=False, content=str(error))


type ToolCallable = Callable[..., ActionResult | Awaitable[ActionResult]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str | None
    fn: ToolCallable
    param_model: type[ToolParams] | None = None
    kind: ActionKind = ActionKind.GENERIC

    def status(self, args: dict[str, Any]) -> str | None:
        """Spoken status the LLM generated for this call, or ``None``.

        Invalid arguments yield ``None`` instead of raising; the call itself
        will surface the validation error when it executes.
        """
        if self.param_model is None:
            return None
        try:
            params = self.param_model.model_validate(args)
        except ValidationError:
            return None
        return params.status

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
