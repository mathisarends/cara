import builtins
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from cara.tools.di import ToolContext
from cara.tools.executor import ToolExecutor
from cara.tools.params import DoneParams
from cara.tools.schemas import ToolSchema
from cara.tools.views import ActionResult, Tool


class Tools:
    def __init__(self, context: ToolContext | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._context = context if context is not None else ToolContext()
        self._executor = ToolExecutor(self._tools, self._context)

        self._register_default_tools()

    def set_context(self, context: ToolContext) -> None:
        self._context = context
        self._executor.set_context(context)

    def provide(self, *dependencies: object) -> None:
        self._context.provide(*dependencies)

    def resolve[T](self, expected_type: type[T]) -> T | None:
        return self._context.resolve(expected_type)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def action[P: BaseModel](
        self,
        description: str | None = None,
        name: str | None = None,
        *,
        params: type[P] | None = None,
        status_label: Callable[[P], str] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._register(
                Tool(
                    name=name or fn.__name__,
                    description=description,
                    fn=fn,
                    param_model=params,
                    status_label=status_label,
                )
            )
            return fn

        return decorator

    def _register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    async def execute(self, name: str, args: dict[str, Any] | None = None) -> ActionResult:
        return await self._executor.execute(name, args)

    def to_schema(self) -> builtins.list[ToolSchema]:
        return [tool.to_schema() for tool in self._tools.values()]

    def _register_default_tools(self) -> None:
        @self.action(
            description="Mark the current task as done.",
            params=DoneParams,
            status_label=lambda _params: "Done",
        )
        async def done(_params: DoneParams) -> ActionResult:
            return ActionResult.success("Done.")
