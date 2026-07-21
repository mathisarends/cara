import builtins
from collections.abc import Callable
from typing import Any

from cara.audio import AudioPlayer
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
    SetAudioOutputParams,
    ToolParams,
    WriteFileParams,
)
from cara.tools.schemas import ToolSchema
from cara.tools.views import ActionKind, ActionResult, Tool, ToolAvailability, ToolDescription


def _multiple_audio_outputs_available(context: ToolContext) -> bool:
    player = context.resolve(AudioPlayer)
    return player is not None and len(player.available_outputs) > 1


def _audio_output_tool_description(context: ToolContext) -> str:
    player = context.resolve(AudioPlayer)
    if player is None:
        return "Switch audio playback to another configured output strategy."
    available = ", ".join(output.value for output in player.available_outputs)
    return f"Switch audio playback to another configured output strategy. Available output names: {available}."


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

    def _register_default_tools(self) -> None:
        self._register_end_session_tool()
        self._register_load_skill_tool()
        self._register_set_audio_output_tool()
        self._register_file_system_tools()

    def _register_end_session_tool(self) -> None:
        @self.action(
            description=(
                "End the conversation when the user says goodbye or otherwise signals "
                "they are finished. Provide a short spoken farewell."
            ),
            params=EndSessionParams,
            kind=ActionKind.END_SESSION,
        )
        async def end_session(params: EndSessionParams) -> ActionResult:
            try:
                return ActionResult.success(params.farewell)
            except Exception as error:
                return ActionResult.fail(error)

    def _register_load_skill_tool(self) -> None:
        @self.action(
            description=(
                "Load a skill's full instructions into context before carrying out a "
                "task it covers. Call this first whenever a request matches one of the "
                "skills listed under <available_skills>, then follow the loaded instructions."
            ),
            params=LoadSkillParams,
        )
        async def load_skill(params: LoadSkillParams, repository: Inject[SkillRepository]) -> ActionResult:
            try:
                skill = repository.get(params.name)
                if skill is None:
                    available = ", ".join(repository.names())
                    return ActionResult.fail(f"Unknown skill '{params.name}'. Available: {available}")
                return ActionResult.success(skill.instructions)
            except Exception as error:
                return ActionResult.fail(error)

    def _register_set_audio_output_tool(self) -> None:
        @self.action(
            description=_audio_output_tool_description,
            params=SetAudioOutputParams,
            available_when=_multiple_audio_outputs_available,
        )
        async def set_audio_output(
            params: SetAudioOutputParams,
            player: Inject[AudioPlayer],
        ) -> ActionResult:
            try:
                player.set_output(params.output)
                return ActionResult.success(f"Audio output switched to {params.output.value!r}.")
            except Exception as error:
                return ActionResult.fail(error)

    def _register_file_system_tools(self) -> None:
        @self.action(
            description=(
                "List files and directories under a path so you can see the workspace "
                "layout before reading or editing. Directories end with a trailing slash."
            ),
            params=ListFilesParams,
        )
        async def list_files(params: ListFilesParams, file_system: Inject[FileSystem]) -> ActionResult:
            try:
                if not file_system.is_dir(params.path):
                    return ActionResult.fail(f"'{params.path}' is not a directory.")
                entries = file_system.tree(params.path)
                return ActionResult.success("\n".join(entries) if entries else "(empty)")
            except Exception as error:
                return ActionResult.fail(error)

        @self.action(
            description="Read a text file's full contents.",
            params=ReadFileParams,
        )
        async def read_file(params: ReadFileParams, file_system: Inject[FileSystem]) -> ActionResult:
            try:
                if not file_system.exists(params.path):
                    return ActionResult.fail(f"'{params.path}' does not exist.")
                return ActionResult.success(file_system.read_text(params.path))
            except Exception as error:
                return ActionResult.fail(error)

        @self.action(
            description=(
                "Create a file or overwrite it entirely with new content. Prefer edit_file "
                "for small changes to an existing file."
            ),
            params=WriteFileParams,
        )
        async def write_file(params: WriteFileParams, file_system: Inject[FileSystem]) -> ActionResult:
            try:
                file_system.write_text(params.path, params.content)
                return ActionResult.success(f"Wrote {params.path}.")
            except Exception as error:
                return ActionResult.fail(error)

        @self.action(
            description="Replace an exact snippet in an existing file. old_text must occur exactly once.",
            params=EditFileParams,
        )
        async def edit_file(params: EditFileParams, file_system: Inject[FileSystem]) -> ActionResult:
            try:
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
            except Exception as error:
                return ActionResult.fail(error)
