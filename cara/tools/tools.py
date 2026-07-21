from collections.abc import Callable
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from cara.audio import AudioPlayer
from cara.file_system import FileSystem, LocalFileSystem, Workspace
from cara.skills import Skills
from cara.tools.di import Inject, ToolContext
from cara.tools.executor import ToolExecutor
from cara.tools.handler import BashSandbox, BashSandboxError, DockerBashSandbox, Location, OpenMeteoClient
from cara.tools.middleware.defaults import default_tool_middlewares
from cara.tools.params import (
    BashParams,
    EditFileParams,
    EndSessionParams,
    ListFilesParams,
    LoadSkillParams,
    ReadFileParams,
    SetAudioOutputParams,
    SetVolumeParams,
    ToolParams,
    WeatherParams,
    WriteFileParams,
)
from cara.tools.schemas import ToolSchema
from cara.tools.views import ActionKind, ActionResult, Tool, ToolAvailability, ToolDescription


def _multiple_audio_outputs_available(context: ToolContext) -> bool:
    player = context.resolve(AudioPlayer)
    return player is not None and len(player.available_outputs) > 1


def _audio_player_available(context: ToolContext) -> bool:
    return context.resolve(AudioPlayer) is not None


def _weather_available(context: ToolContext) -> bool:
    return context.resolve(OpenMeteoClient) is not None and context.resolve(Location) is not None


def _audio_output_tool_description(context: ToolContext) -> str:
    player = context.resolve(AudioPlayer)
    if player is None:
        return "Switch audio playback to another configured output strategy."
    available = ", ".join(output.value for output in player.available_outputs)
    return f"Switch audio playback to another configured output strategy. Available output names: {available}."


def _default_workspace() -> Workspace:
    root = Path(gettempdir()) / "cara" / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return Workspace(root)


class Tools:
    def __init__(
        self,
        context: ToolContext | None = None,
        *,
        workspace: Workspace | None = None,
        bash_allowed_commands: tuple[str, ...] = (),
        bash_sandbox: BashSandbox | None = None,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        initial_context = context or ToolContext()
        configured_workspace = initial_context.resolve(Workspace)
        if workspace is not None and configured_workspace is not None and workspace.root != configured_workspace.root:
            raise ValueError("ToolContext and Tools specify different workspaces")
        self._workspace = workspace or configured_workspace or _default_workspace()
        self._bash_sandbox = bash_sandbox if bash_sandbox is not None else DockerBashSandbox()
        self._context = self._prepare_context(initial_context)

        self._executor = ToolExecutor(
            self._tools,
            self._context,
            default_tool_middlewares(bash_allowed_commands=bash_allowed_commands),
        )
        self._register_default_tools()

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

    def to_schema(self) -> list[ToolSchema]:
        return [tool.to_schema(self._context) for tool in self._tools.values() if tool.is_available(self._context)]

    def _register_default_tools(self) -> None:
        @self.action(
            description=(
                "End the conversation when the user says goodbye or otherwise signals "
                "they are finished. Provide a short spoken farewell."
            ),
            params=EndSessionParams,
            kind=ActionKind.END_SESSION,
        )
        async def end_session(params: EndSessionParams) -> ActionResult:
            return ActionResult.success(params.farewell)

        @self.action(
            description=(
                "Load a skill's full instructions into context before carrying out a "
                "task it covers. Call this first whenever a request matches one of the "
                "skills listed under <available_skills>, then follow the loaded instructions."
            ),
            params=LoadSkillParams,
        )
        async def load_skill(params: LoadSkillParams, skills: Inject[Skills]) -> ActionResult:
            skill = skills.get(params.name)
            if skill is None:
                available = ", ".join(skills.names())
                return ActionResult.fail(f"Unknown skill '{params.name}'. Available: {available}")
            return ActionResult.success(skill.instructions)

        @self.action(
            description=_audio_output_tool_description,
            params=SetAudioOutputParams,
            available_when=_multiple_audio_outputs_available,
        )
        async def set_audio_output(
            params: SetAudioOutputParams,
            player: Inject[AudioPlayer],
        ) -> ActionResult:
            player.set_output(params.output)
            return ActionResult.success(f"Audio output switched to {params.output.value!r}.")

        @self.action(
            description=(
                "Frage die aktuelle Wiedergabelautstärke des aktiven Audio-Ausgangs ab, als Wert von 0.0 bis 1.0."
            ),
            kind=ActionKind.READ,
            available_when=_audio_player_available,
        )
        async def get_volume(player: Inject[AudioPlayer]) -> ActionResult:
            level = await player.get_volume()
            return ActionResult.success(f"{level:.2f}")

        @self.action(
            description=(
                "Stelle die Wiedergabelautstärke des aktiven Audio-Ausgangs auf einen Zielwert. "
                "Frage vorher get_volume ab, um den aktuellen Wert zu kennen, z. B. um ihn schrittweise "
                "lauter oder leiser zu machen."
            ),
            params=SetVolumeParams,
            available_when=_audio_player_available,
        )
        async def set_volume(params: SetVolumeParams, player: Inject[AudioPlayer]) -> ActionResult:
            await player.set_volume(params.level)
            return ActionResult.success(f"Lautstärke ist jetzt {round(params.level * 100)}%.")

        @self.action(
            description=(
                "Frage das aktuelle Wetter ab. Gib optional einen Ort an; ohne Ort gilt der "
                "aktuelle Standort aus dem Kontext."
            ),
            params=WeatherParams,
            kind=ActionKind.READ,
            available_when=_weather_available,
        )
        async def weather(
            params: WeatherParams,
            client: Inject[OpenMeteoClient],
            location: Inject[Location],
        ) -> ActionResult:
            target = location
            if params.location:
                found = await client.locate(params.location)
                if found is None:
                    return ActionResult.fail(f"Ich konnte den Ort '{params.location}' nicht finden.")
                target = found
            report = await client.current(target)
            return ActionResult.success(report.summary())

        @self.action(
            description=(
                "Execute a Bash command in an isolated Docker container. The container has no network, "
                "has limited resources, and can only write to the workspace."
            ),
            params=BashParams,
            kind=ActionKind.DESTRUCTIVE,
        )
        async def bash(params: BashParams, workspace: Inject[Workspace]) -> ActionResult:
            try:
                result = await self._bash_sandbox.run(params.command, workspace)
            except BashSandboxError as error:
                return ActionResult.fail(error)
            if result.return_code != 0:
                detail = f"\n{result.output}" if result.output else ""
                return ActionResult.fail(f"Command exited with status {result.return_code}.{detail}")
            return ActionResult.success(result.output or "(no output)")

        @self.action(
            description=(
                "List files and directories under a path so you can see the workspace "
                "layout before reading or editing. Directories end with a trailing slash."
            ),
            params=ListFilesParams,
            kind=ActionKind.READ,
        )
        async def list_files(params: ListFilesParams, file_system: Inject[FileSystem]) -> ActionResult:
            if not file_system.is_dir(params.path):
                return ActionResult.fail(f"'{params.path}' is not a directory.")
            entries = []
            for name in file_system.list_dir(params.path):
                child = f"{params.path.rstrip('/')}/{name}"
                entries.append(f"{name}/" if file_system.is_dir(child) else name)
            return ActionResult.success("\n".join(entries) if entries else "(empty)")

        @self.action(
            description="Read a text file's full contents.",
            params=ReadFileParams,
            kind=ActionKind.READ,
        )
        async def read_file(params: ReadFileParams, file_system: Inject[FileSystem]) -> ActionResult:
            if not file_system.exists(params.path):
                return ActionResult.fail(f"'{params.path}' does not exist.")
            return ActionResult.success(file_system.read_text(params.path))

        @self.action(
            description=(
                "Create a file or overwrite it entirely with new content. Prefer edit_file "
                "for small changes to an existing file."
            ),
            params=WriteFileParams,
            kind=ActionKind.MUTATE,
        )
        async def write_file(params: WriteFileParams, file_system: Inject[FileSystem]) -> ActionResult:
            file_system.write_text(params.path, params.content)
            return ActionResult.success(f"Wrote {params.path}.")

        @self.action(
            description="Replace an exact snippet in an existing file. old_text must occur exactly once.",
            params=EditFileParams,
            kind=ActionKind.MUTATE,
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
