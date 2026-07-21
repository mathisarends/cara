import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Self

from pydantic import ValidationError

from cara.tools.di import ToolContext
from cara.tools.params import ToolParams
from cara.tools.schemas import ToolSchema, ToolSchemaBuilder


class ActionKind(Enum):
    GENERIC = auto()
    READ = auto()
    MUTATE = auto()
    DESTRUCTIVE = auto()
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

    @property
    def is_success(self) -> bool:
        return self.ok

    def truncated(self, max_chars: int, *, note: str) -> Self:
        if self.content is None or len(self.content) <= max_chars:
            return self
        suffix = f"\n\n[{note}]"
        if len(suffix) >= max_chars:
            return type(self)(ok=self.ok, content=suffix[:max_chars])
        return type(self)(ok=self.ok, content=f"{self.content[: max_chars - len(suffix)]}{suffix}")


type ToolCallable = Callable[..., ActionResult | Awaitable[ActionResult]]
type ToolDescription = str | Callable[[ToolContext], str]
type ToolAvailability = Callable[[ToolContext], bool]


@dataclass(frozen=True)
class Tool:
    name: str
    description: ToolDescription | None
    fn: ToolCallable
    param_model: type[ToolParams] | None = None
    kind: ActionKind = ActionKind.GENERIC
    available_when: ToolAvailability | None = None

    def is_available(self, context: ToolContext) -> bool:
        return self.available_when is None or self.available_when(context)

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

    def to_schema(self, context: ToolContext) -> ToolSchema:
        description = self.description(context) if callable(self.description) else self.description
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": description or "",
                "parameters": ToolSchemaBuilder(self.fn, self.param_model).build(),
            },
        }
