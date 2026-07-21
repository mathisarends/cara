import builtins
from collections.abc import Callable
from typing import Any

from cara.file_system import FileSystem
from cara.skills import SkillRepository
from cara.tools.di import Inject, ToolContext
from cara.tools.executor import ToolExecutor
from cara.tools.params import (
    EditFileParams,
    EndSessionParams,
    ListFilesParams,
    LoadSkillParams,
    ReadFileParams,
    ToolParams,
    WriteFileParams,
)
from cara.tools.schemas import ToolSchema
from cara.tools.views import ActionKind, ActionResult, Tool


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

    def action[P: ToolParams](
        self,
        description: str | None = None,
        name: str | None = None,
        *,
        params: type[P] | None = None,
        kind: ActionKind = ActionKind.GENERIC,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._register(
                Tool(
                    name=name or fn.__name__,
                    description=description,
                    fn=fn,
                    param_model=params,
                    kind=kind,
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
        self._register_end_session_tool()
        self._register_load_skill_tool()
        self._register_file_system_tools()

    def _register_end_session_tool(self) -> None:
        @self.action(
            name="end_session",
            description=(
                "End the conversation when the user says goodbye or otherwise signals "
                "they are finished. Provide a short spoken farewell."
            ),
            params=EndSessionParams,
            kind=ActionKind.END_SESSION,
        )
        async def end_session(params: EndSessionParams) -> ActionResult:
            return ActionResult.success(params.farewell)

    def _register_load_skill_tool(self) -> None:
        @self.action(
            name="load_skill",
            description=(
                "Load a skill's full instructions into context before carrying out a "
                "task it covers. Call this first whenever a request matches one of the "
                "skills listed under <available_skills>, then follow the loaded instructions."
            ),
            params=LoadSkillParams,
        )
        async def load_skill(params: LoadSkillParams, repository: Inject[SkillRepository]) -> ActionResult:
            skill = repository.get(params.name)
            if skill is None:
                available = ", ".join(repository.names())
                return ActionResult.fail(f"Unknown skill '{params.name}'. Available: {available}")
            return ActionResult.success(skill.instructions)

    def _register_file_system_tools(self) -> None:
        @self.action(
            name="list_files",
            description=(
                "List files and directories under a path so you can see the workspace "
                "layout before reading or editing. Directories end with a trailing slash."
            ),
            params=ListFilesParams,
        )
        async def list_files(params: ListFilesParams, file_system: Inject[FileSystem]) -> ActionResult:
            if not file_system.is_dir(params.path):
                return ActionResult.fail(f"'{params.path}' is not a directory.")
            entries = file_system.tree(params.path)
            return ActionResult.success("\n".join(entries) if entries else "(empty)")

        @self.action(
            name="read_file",
            description="Read a text file's full contents.",
            params=ReadFileParams,
        )
        async def read_file(params: ReadFileParams, file_system: Inject[FileSystem]) -> ActionResult:
            if not file_system.exists(params.path):
                return ActionResult.fail(f"'{params.path}' does not exist.")
            return ActionResult.success(file_system.read_text(params.path))

        @self.action(
            name="write_file",
            description=(
                "Create a file or overwrite it entirely with new content. Prefer edit_file "
                "for small changes to an existing file."
            ),
            params=WriteFileParams,
        )
        async def write_file(params: WriteFileParams, file_system: Inject[FileSystem]) -> ActionResult:
            file_system.write_text(params.path, params.content)
            return ActionResult.success(f"Wrote {params.path}.")

        @self.action(
            name="edit_file",
            description="Replace an exact snippet in an existing file. old_text must occur exactly once.",
            params=EditFileParams,
        )
        async def edit_file(params: EditFileParams, file_system: Inject[FileSystem]) -> ActionResult:
            if not file_system.exists(params.path):
                return ActionResult.fail(f"'{params.path}' does not exist.")
            content = file_system.read_text(params.path)
            occurrences = content.count(params.old_text)
            if occurrences == 0:
                return ActionResult.fail("old_text was not found in the file.")
            if occurrences > 1:
                return ActionResult.fail(
                    f"old_text is not unique ({occurrences} matches); include more surrounding context."
                )
            file_system.write_text(params.path, content.replace(params.old_text, params.new_text))
            return ActionResult.success(f"Edited {params.path}.")
