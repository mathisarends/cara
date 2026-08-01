from pathlib import Path
from tempfile import gettempdir

import agenttoolkit
from agenttoolkit import (
    ActionResult,
    Inject,
    Skills,
    ToolContext,
    ToolEffect,
    description_from_context,
    provided,
    requires,
)
from agenttoolkit.builtins import (
    DockerSandbox,
    LocalWorkspace,
    Sandbox,
    SandboxError,
    SandboxLimits,
    SandboxPolicy,
    Workspace,
    WorkspaceError,
)

from cara.audio import AudioPlayer
from cara.tools.handler import IpLocationClient, OpenMeteoClient, TavilySearchClient
from cara.tools.params import (
    BashParams,
    EditFileParams,
    EndSessionParams,
    ListFilesParams,
    LoadSkillParams,
    ReadFileParams,
    SetAudioOutputParams,
    SetVolumeParams,
    WeatherParams,
    WebSearchParams,
    WriteFileParams,
)

_BASH_IMAGE = "cara-bash-sandbox:latest"
_END_SESSION_TAG = "end_session"


def _default_workspace() -> LocalWorkspace:
    return LocalWorkspace(Path(gettempdir()) / "cara" / "workspace", max_file_bytes=1_000_000)


def _default_sandbox(workspace: Workspace) -> DockerSandbox:
    return DockerSandbox(
        _BASH_IMAGE,
        SandboxPolicy.for_workspace(
            workspace.root,
            limits=SandboxLimits(
                timeout_seconds=15,
                max_output_bytes=1_000_000,
                memory_bytes=256 * 1024 * 1024,
                pids=64,
                cpus=1,
            ),
            environment={"HOME": "/tmp"},
        ),
        shell="/bin/bash",
    )


class Tools(agenttoolkit.Tools):
    """Cara's tool catalog, backed entirely by agenttoolkit."""

    def __init__(
        self,
        context: ToolContext | None = None,
        *,
        workspace: Workspace | None = None,
        sandbox: Sandbox | None = None,
    ) -> None:
        initial_context = context or ToolContext()
        configured_workspace = initial_context.resolve(Workspace)
        if workspace is not None and configured_workspace is not None and workspace.root != configured_workspace.root:
            raise ValueError("ToolContext and Tools specify different workspaces")

        selected_workspace = workspace or configured_workspace or _default_workspace()
        selected_sandbox = sandbox or initial_context.resolve(Sandbox) or _default_sandbox(selected_workspace)
        if configured_workspace is None:
            initial_context.provide(selected_workspace)
        if initial_context.resolve(Sandbox) is None:
            initial_context.provide(selected_sandbox)

        super().__init__(context=initial_context)
        self._register_default_tools()

    def provide(self, *dependencies: object) -> None:
        if self._context is None:
            self._context = ToolContext()
        self._context.provide(*dependencies)

    def _register_default_tools(self) -> None:
        @self.action(
            description=(
                "End the conversation when the user says goodbye or otherwise signals "
                "they are finished. Provide a short spoken farewell."
            ),
            params=EndSessionParams,
            tags=(_END_SESSION_TAG,),
        )
        async def end_session(params: EndSessionParams) -> ActionResult:
            return ActionResult.success(params.farewell)

        @self.action(
            description=(
                "Load a skill's full instructions into context before carrying out a task it covers. "
                "Call this first whenever a request matches one of the listed skills."
            ),
            params=LoadSkillParams,
            available_when=requires(Skills, predicate=lambda skills: len(skills) > 0),
        )
        async def load_skill(params: LoadSkillParams, skills: Inject[Skills]) -> ActionResult:
            loaded = skills.load(params.name)
            return ActionResult.success(loaded.instructions)

        @self.action(
            description=description_from_context(
                AudioPlayer,
                render=lambda player: (
                    "Switch audio playback to another configured audio sink. "
                    f"Available output names: {player.describe_outputs()}."
                ),
                fallback="Switch audio playback to another configured audio sink.",
            ),
            params=SetAudioOutputParams,
            available_when=requires(AudioPlayer, predicate=lambda player: player.has_multiple_outputs),
        )
        async def set_audio_output(params: SetAudioOutputParams, player: Inject[AudioPlayer]) -> ActionResult:
            player.set_output(params.output)
            return ActionResult.success(f"Audio output switched to {params.output.value!r}.")

        @self.action(
            description=(
                "Frage die aktuelle Wiedergabelautstärke des aktiven Audio-Ausgangs ab, als Wert von 0.0 bis 1.0."
            ),
            available_when=provided(AudioPlayer),
        )
        async def get_volume(player: Inject[AudioPlayer]) -> ActionResult:
            level = await player.get_volume()
            return ActionResult.success(f"{level:.2f}")

        @self.action(
            description=(
                "Stelle die Wiedergabelautstärke des aktiven Audio-Ausgangs auf einen Zielwert. "
                "Frage vorher get_volume ab, um den aktuellen Wert zu kennen."
            ),
            params=SetVolumeParams,
            available_when=provided(AudioPlayer),
        )
        async def set_volume(params: SetVolumeParams, player: Inject[AudioPlayer]) -> ActionResult:
            await player.set_volume(params.level)
            return ActionResult.success(f"Lautstärke ist jetzt {round(params.level * 100)}%.")

        @self.action(
            description="Frage das aktuelle Wetter ab. Uses the current location.",
            params=WeatherParams,
            effects=(ToolEffect.NETWORK,),
        )
        async def weather(
            params: WeatherParams,
            location_client: Inject[IpLocationClient],
            client: Inject[OpenMeteoClient],
        ) -> ActionResult:
            del params
            location = await location_client.current()
            report = await client.current(location)
            return ActionResult.success(report.summary())

        @self.action(
            description="Durchsuche das Internet nach aktuellen Informationen, News oder Fakten.",
            params=WebSearchParams,
            effects=(ToolEffect.NETWORK,),
        )
        async def web_search(params: WebSearchParams, client: Inject[TavilySearchClient]) -> ActionResult:
            response = await client.search(params.query, max_results=params.max_results)
            return ActionResult.success(response.summary())

        @self.action(
            description="Execute a Bash command in the isolated workspace sandbox.",
            params=BashParams,
            effects=(ToolEffect.SPAWNS_PROCESS, ToolEffect.WRITES_WORKSPACE),
        )
        async def bash(params: BashParams, workspace: Inject[Workspace], sandbox: Inject[Sandbox]) -> ActionResult:
            try:
                result = await sandbox.execute(params.command, cwd=workspace.root)
            except SandboxError as error:
                return ActionResult.fail(error)
            if not result.ok:
                detail = f"\n{result.output}" if result.output else ""
                return ActionResult.fail(f"Command exited with status {result.returncode}.{detail}")
            return ActionResult.success(result.output.rstrip() or "(no output)")

        @self.action(
            description="List files and directories under a workspace path. Directories end with a slash.",
            params=ListFilesParams,
            effects=(ToolEffect.READS_WORKSPACE,),
        )
        async def list_files(params: ListFilesParams, workspace: Inject[Workspace]) -> ActionResult:
            try:
                entries = await workspace.list_dir(params.path)
            except (OSError, WorkspaceError) as error:
                return ActionResult.fail(error)
            rendered = [f"{entry.path}/" if entry.is_dir else entry.path for entry in entries]
            return ActionResult.success("\n".join(rendered) if rendered else "(empty)")

        @self.action(
            description="Read a text file's full contents.",
            params=ReadFileParams,
            effects=(ToolEffect.READS_WORKSPACE,),
        )
        async def read_file(params: ReadFileParams, workspace: Inject[Workspace]) -> ActionResult:
            try:
                content = await workspace.read_file(params.path)
            except (OSError, WorkspaceError) as error:
                return ActionResult.fail(error)
            return ActionResult.success(content)

        @self.action(
            description="Create a file or overwrite it entirely with new content.",
            params=WriteFileParams,
            effects=(ToolEffect.WRITES_WORKSPACE,),
        )
        async def write_file(params: WriteFileParams, workspace: Inject[Workspace]) -> ActionResult:
            try:
                await workspace.write_file(params.path, params.content)
            except (OSError, WorkspaceError) as error:
                return ActionResult.fail(error)
            return ActionResult.success(f"Wrote {params.path}.")

        @self.action(
            description="Replace an exact snippet in an existing file. old_text must occur exactly once.",
            params=EditFileParams,
            effects=(ToolEffect.WRITES_WORKSPACE,),
        )
        async def edit_file(params: EditFileParams, workspace: Inject[Workspace]) -> ActionResult:
            try:
                await workspace.edit_file(params.path, params.old_text, params.new_text)
            except (OSError, WorkspaceError) as error:
                return ActionResult.fail(error)
            return ActionResult.success(f"Edited {params.path}.")
