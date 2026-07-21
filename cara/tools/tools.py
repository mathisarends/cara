import builtins
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cara.file_system import FileSystem, LocalFileSystem, Workspace
from cara.tools.di import ToolContext
from cara.tools.executor import ToolExecutor
from cara.tools.middleware import (
    BashPolicy,
    BashPolicyMiddleware,
    ContentSizeMiddleware,
    ErrorBoundaryMiddleware,
    PathPolicy,
    PathPolicyMiddleware,
    ResultLimitMiddleware,
    ToolMiddleware,
)
from cara.tools.params import ToolParams
from cara.tools.schemas import ToolSchema
from cara.tools.toolsets import AudioTools, BashTools, CoreTools, FileSystemTools, Toolset
from cara.tools.views import ActionKind, ActionResult, Tool, ToolAvailability, ToolDescription


class Tools:
    _SENSITIVE_PATHS = (
        ".env",
        "**/.env",
        ".git",
        ".git/**",
        "**/.git/**",
        "*.pem",
        "**/*.pem",
        "id_rsa*",
        "**/id_rsa*",
    )

    def __init__(
        self,
        context: ToolContext | None = None,
        *,
        workspace: Workspace | None = None,
        middlewares: tuple[ToolMiddleware, ...] = (),
        toolsets: tuple[Toolset, ...] | None = None,
        bash_allowed_commands: tuple[str, ...] = (),
    ) -> None:
        self._tools: dict[str, Tool] = {}
        initial_context = context or ToolContext()
        configured_workspace = initial_context.resolve(Workspace)
        if workspace is not None and configured_workspace is not None and workspace.root != configured_workspace.root:
            raise ValueError("ToolContext and Tools specify different workspaces")
        self._workspace = workspace or configured_workspace or Workspace(Path.cwd())
        self._context = self._prepare_context(initial_context)
        middleware_chain: list[ToolMiddleware] = [
            # Order is load-bearing: errors wrap the whole chain; response limiting
            # wraps custom middleware, policy, and invocation. Custom tracing therefore
            # sees original results before they are truncated and observes policy denials.
            ErrorBoundaryMiddleware(),
            ResultLimitMiddleware(),
            *middlewares,
            PathPolicyMiddleware(PathPolicy(denied=self._SENSITIVE_PATHS)),
            ContentSizeMiddleware(),
            BashPolicyMiddleware(BashPolicy(bash_allowed_commands)),
        ]
        self._executor = ToolExecutor(self._tools, self._context, middleware_chain)

        active_toolsets = (
            toolsets if toolsets is not None else (CoreTools(), AudioTools(), BashTools(), FileSystemTools())
        )
        for toolset in active_toolsets:
            toolset.register(self)

    def set_context(self, context: ToolContext) -> None:
        self._context = self._prepare_context(context)
        self._executor.set_context(self._context)

    def _prepare_context(self, context: ToolContext) -> ToolContext:
        configured_workspace = context.resolve(Workspace)
        if configured_workspace is not None and configured_workspace.root != self._workspace.root:
            raise ValueError("ToolContext and Tools specify different workspaces")

        if configured_workspace is None:
            context.provide(self._workspace)
        if context.resolve(FileSystem) is None:
            context.provide(LocalFileSystem(self._workspace))
        return context

    def provide(self, *dependencies: object) -> None:
        self._context.provide(*dependencies)

    def resolve[T](self, expected_type: type[T]) -> T | None:
        return self._context.resolve(expected_type)

    def get(self, name: str) -> Tool | None:
        tool = self._tools.get(name)
        if tool is None or not tool.is_available(self._context):
            return None
        return tool

    def action[P: ToolParams](
        self,
        description: ToolDescription | None = None,
        name: str | None = None,
        *,
        params: type[P] | None = None,
        kind: ActionKind = ActionKind.GENERIC,
        available_when: ToolAvailability | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._register(
                Tool(
                    name=name or fn.__name__,
                    description=description,
                    fn=fn,
                    param_model=params,
                    kind=kind,
                    available_when=available_when,
                )
            )
            return fn

        return decorator

    def _register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    async def execute(self, name: str, args: dict[str, Any] | None = None) -> ActionResult:
        return await self._executor.execute(name, args)

    def to_schema(self) -> builtins.list[ToolSchema]:
        return [tool.to_schema(self._context) for tool in self._tools.values() if tool.is_available(self._context)]
