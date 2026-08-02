from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import gettempdir

import agenttoolkit
from agenttoolkit import (
    CallLoggingMiddleware,
    ErrorBoundaryMiddleware,
    Inject,
    Skills,
    ToolContext,
    description_from_context,
    provided,
    requires,
)
from agenttoolkit.builtins import (
    CommandDefaults,
    CommandLimits,
    CommandRunner,
    DockerSandbox,
    LocalWorkspace,
    SandboxLimits,
    SandboxPolicy,
    Workspace,
)
from agenttoolkit.builtins.fs import Entry

from cara.audio import AudioPlayer
from cara.memory import HybridMemoryResult, HybridMemorySearch
from cara.tools.handler import IpLocationClient, OpenMeteoClient, TavilySearchClient, WeatherReport
from cara.tools.params import (
    BashParams,
    EditFileParams,
    GlobParams,
    GrepParams,
    ListFilesParams,
    LoadSkillParams,
    ReadFileParams,
    SearchMemoryParams,
    SetAudioOutputParams,
    SetVolumeParams,
    WeatherParams,
    WebSearchParams,
    WriteFileParams,
)

_BASH_IMAGE = "cara-bash-sandbox:latest"
_MEMORY_ROOT = Path(__file__).resolve().parent.parent / "prompt" / "content"


def create_tool_context(
    *dependencies: object,
    workspace: Workspace | None = None,
    sandbox: CommandRunner | None = None,
    workspace_mounts: Mapping[str, Path] | None = None,
) -> ToolContext:
    if workspace is not None and workspace_mounts:
        raise ValueError("Use either workspace or workspace_mounts, not both.")
    selected_workspace = workspace or _default_workspace(workspace_mounts)
    selected_sandbox = sandbox or _default_sandbox(selected_workspace)
    return ToolContext(selected_workspace, selected_sandbox, *dependencies)


def _default_workspace(additional_mounts: Mapping[str, Path] | None = None) -> LocalWorkspace:
    mounts = dict(additional_mounts or {})
    if "/memory" in mounts:
        raise ValueError("The /memory workspace mount is reserved.")
    mounts["/memory"] = _MEMORY_ROOT
    return LocalWorkspace(
        Path(gettempdir()) / "cara" / "workspace",
        mounts=mounts,
        max_file_bytes=1_000_000,
    )


def _default_sandbox(workspace: Workspace) -> DockerSandbox:
    return DockerSandbox(
        _BASH_IMAGE,
        defaults=CommandDefaults(
            environment={"HOME": "/tmp"},
            limits=CommandLimits(timeout_seconds=15, max_output_bytes=1_000_000),
        ),
        policy=SandboxPolicy.for_workspace(
            workspace.root,
            limits=SandboxLimits(
                memory_bytes=256 * 1024 * 1024,
                pids=64,
                cpus=1,
            ),
        ),
        shell="/bin/bash",
    )


def create_tools(context: ToolContext | None = None) -> agenttoolkit.Tools:
    selected_context = context if context is not None else create_tool_context()
    tools = _new_tools(selected_context)
    register_tools(tools)
    return tools


def _new_tools(context: ToolContext) -> agenttoolkit.Tools:
    return agenttoolkit.Tools(
        context=context,
        middleware=(CallLoggingMiddleware(), ErrorBoundaryMiddleware()),
    )


def build_tools(
    *dependencies: object,
    skills: Skills | None = None,
    workspace: Workspace | None = None,
    workspace_mounts: Mapping[str, Path] | None = None,
    tools: agenttoolkit.Tools | None = None,
) -> agenttoolkit.Tools:
    configured_dependencies = [*dependencies, IpLocationClient(), OpenMeteoClient(), TavilySearchClient()]
    if skills is not None:
        configured_dependencies.append(skills)
    tool_context = create_tool_context(
        *configured_dependencies,
        workspace=workspace,
        workspace_mounts=workspace_mounts,
    )
    if tools is None:
        return create_tools(tool_context)
    configured_tools = _new_tools(tool_context)
    configured_tools.merge(tools)
    return configured_tools


def register_tools(tools: agenttoolkit.Tools) -> None:
    @tools.action(
        description=(
            "Load a skill's full instructions into context before carrying out a task it covers. "
            "Call this first whenever a request matches one of the listed skills."
        ),
        params=LoadSkillParams,
        available_when=requires(Skills, predicate=lambda skills: len(skills) > 0),
    )
    async def load_skill(params: LoadSkillParams, skills: Inject[Skills]) -> str:
        loaded = skills.load(params.name)
        return loaded.instructions

    @tools.action(
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
    async def set_audio_output(params: SetAudioOutputParams, player: Inject[AudioPlayer]) -> str:
        player.set_output(params.output)
        return f"Audio output switched to {params.output.value!r}."

    @tools.action(
        description=(
            "Frage die aktuelle Wiedergabelautstärke des aktiven Audio-Ausgangs ab, als Wert von 0.0 bis 1.0."
        ),
        available_when=provided(AudioPlayer),
    )
    async def get_volume(player: Inject[AudioPlayer]) -> str:
        level = await player.get_volume()
        return f"{level:.2f}"

    @tools.action(
        description=(
            "Stelle die Wiedergabelautstärke des aktiven Audio-Ausgangs auf einen Zielwert. "
            "Frage vorher get_volume ab, um den aktuellen Wert zu kennen."
        ),
        params=SetVolumeParams,
        available_when=provided(AudioPlayer),
    )
    async def set_volume(params: SetVolumeParams, player: Inject[AudioPlayer]) -> str:
        await player.set_volume(params.level)
        return f"Lautstärke ist jetzt {round(params.level * 100)}%."

    @tools.action(
        description=(
            "Frage das Wetter ab, für den aktuellen Standort oder einen angegebenen Ort. "
            "Nutze params.location nur, wenn explizit nach einem bestimmten Ort gefragt wird."
        ),
        params=WeatherParams,
    )
    async def weather_report(
        params: WeatherParams,
        location_client: Inject[IpLocationClient],
        client: Inject[OpenMeteoClient],
    ) -> str:
        if params.location:
            location = await client.locate(params.location)
            if location is None:
                return f"Kein Ort namens '{params.location}' gefunden."
        else:
            location = await location_client.current()
        report = await client.current(location)
        return _render_weather_report(report)

    @tools.action(
        description="Durchsuche das Internet nach aktuellen Informationen, News oder Fakten.",
        params=WebSearchParams,
    )
    async def web_search(params: WebSearchParams, client: Inject[TavilySearchClient]) -> str:
        response = await client.search(params.query, max_results=params.max_results)
        return response.summary()

    @tools.action(
        description=(
            "Search older daily notes and durable memory. Returns concise original excerpts "
            "with their source and date, ordered by relevance."
        ),
        params=SearchMemoryParams,
        available_when=provided(HybridMemorySearch),
    )
    async def search_memory(
        params: SearchMemoryParams,
        memory: Inject[HybridMemorySearch],
    ) -> str:
        results = await memory.search(
            params.query,
            limit=params.limit,
            vector_weight=params.vector_weight,
            text_weight=params.text_weight,
        )
        return _render_memory_results(results)

    @tools.action(
        description="Execute a Bash command in the isolated workspace sandbox.",
        params=BashParams,
    )
    async def bash(params: BashParams, workspace: Inject[Workspace], sandbox: Inject[CommandRunner]) -> str:
        result = await sandbox.execute(params.command, cwd=workspace.root)
        result.check_returncode()
        return result.output.rstrip() or "(no output)"

    @tools.action(
        description=(
            "List files and directories under a workspace path. Directories end with a slash. "
            "'/memory' holds Cara's persistent context files; /memory/AGENTS.md explains what "
            "belongs in each file and when to update it."
        ),
        params=ListFilesParams,
    )
    async def list_files(params: ListFilesParams, workspace: Inject[Workspace]) -> str:
        entries = await workspace.list_dir(params.path)
        return _render_entries(entries, empty="(empty)")

    @tools.action(
        description="Find workspace files and directories whose paths match a glob pattern.",
        params=GlobParams,
    )
    async def glob(params: GlobParams, workspace: Inject[Workspace]) -> str:
        entries = await workspace.glob(params.pattern)
        return _render_entries(entries[: params.max_results], empty="(no matches)")

    @tools.action(
        description="Search workspace file contents with a regular expression.",
        params=GrepParams,
    )
    async def grep(params: GrepParams, workspace: Inject[Workspace]) -> str:
        matches = await workspace.grep(
            params.pattern,
            glob=params.glob,
            case_sensitive=params.case_sensitive,
            context_lines=params.context_lines,
            max_matches=params.max_matches,
        )
        rendered: list[str] = []
        for match in matches:
            first_context_line = match.line_number - len(match.context_before)
            rendered.extend(
                f"{match.path}-{line_number}-{line}"
                for line_number, line in enumerate(match.context_before, start=first_context_line)
            )
            rendered.append(f"{match.path}:{match.line_number}:{match.line}")
            rendered.extend(
                f"{match.path}-{line_number}-{line}"
                for line_number, line in enumerate(match.context_after, start=match.line_number + 1)
            )
        return "\n".join(rendered) if rendered else "(no matches)"

    @tools.action(
        description="Read a text file's full contents.",
        params=ReadFileParams,
    )
    async def read_file(params: ReadFileParams, workspace: Inject[Workspace]) -> str:
        content = await workspace.read_file(params.path)
        return content

    @tools.action(
        description="Create a file or overwrite it entirely with new content.",
        params=WriteFileParams,
    )
    async def write_file(params: WriteFileParams, workspace: Inject[Workspace]) -> str:
        await workspace.write_file(params.path, params.content)
        return f"Wrote {params.path}."

    @tools.action(
        description="Replace an exact snippet in an existing file. old_text must occur exactly once.",
        params=EditFileParams,
    )
    async def edit_file(params: EditFileParams, workspace: Inject[Workspace]) -> str:
        await workspace.edit_file(params.path, params.old_text, params.new_text)
        return f"Edited {params.path}."


def _render_weather_report(report: WeatherReport) -> str:
    parts = [f"**{round(report.temperature_c)} °C**"]
    if abs(report.temperature_c - report.apparent_temperature_c) >= 2:
        parts.append(f"gefühlt {round(report.apparent_temperature_c)} °C")
    parts.append(report.description)
    parts.append(f"Wind {round(report.wind_speed_kmh)} km/h")
    summary = f"## Wetter in {report.location_name}\n\n" + ", ".join(parts) + "."

    if not report.hourly:
        return summary

    rows = (
        f"| {hour.time:%H:%M} | {hour.description} | {round(hour.temperature_c)} °C | "
        f"{hour.precipitation_probability}% |"
        for hour in report.hourly
    )
    table = "\n".join(["| Uhrzeit | Wetter | Temp | Regen |", "| --- | --- | --- | --- |", *rows])
    return f"{summary}\n\n{table}"


def _render_entries(entries: Sequence[Entry], *, empty: str) -> str:
    rendered = [f"{entry.path}/" if entry.is_dir else entry.path for entry in entries]
    return "\n".join(rendered) if rendered else empty


def _render_memory_results(results: Sequence[HybridMemoryResult]) -> str:
    if not results:
        return "(no relevant memories found)"

    grouped: dict[str, tuple[str, str | None, list[str]]] = {}
    for result in results:
        document = result.document
        path = document.metadata.get("path")
        source = path if isinstance(path, str) else document.parent_id or document.id
        group_key = document.parent_id or document.id
        created_at = document.created_at.date().isoformat() if document.created_at is not None else None
        text = document.text.strip()

        group = grouped.get(group_key)
        if group is None:
            grouped[group_key] = (source, created_at, [text])
        elif text not in group[2]:
            group[2].append(text)

    rendered = ["Memory excerpts, ordered by relevance:"]
    for source, created_at, excerpts in grouped.values():
        heading = f"[{source}]" if created_at is None else f"[{source} | {created_at}]"
        rendered.append(f"{heading}\n" + "\n\n".join(excerpts))
    return "\n\n".join(rendered)
