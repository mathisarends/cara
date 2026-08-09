from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Self

import agenttoolkit
from agenttoolkit import (
    CallLoggingMiddleware,
    ErrorBoundaryMiddleware,
    Inject,
    Skills,
    ToolContext,
    provided,
    requires,
)
from agenttoolkit.builtins import (
    BindMount,
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
from config import CaraPaths

from agent.memory import HybridMemorySearch, render_memory_results
from agent.tools.handler import (
    IpLocationClient,
    OpenMeteoClient,
    SearchResponse,
    TavilySearchClient,
    WeatherReport,
)
from agent.tools.params import (
    BashParams,
    EditFileParams,
    GlobParams,
    GrepParams,
    ListFilesParams,
    LoadSkillParams,
    ReadFileParams,
    SearchMemoryParams,
    WeatherParams,
    WebSearchParams,
    WriteFileParams,
)

_BASH_IMAGE = "cara-bash-sandbox:latest"


class _ManagedTools(agenttoolkit.Tools):
    def __init__(self, context: ToolContext) -> None:
        super().__init__(
            context=context,
            middleware=(CallLoggingMiddleware(), ErrorBoundaryMiddleware()),
        )
        self._sandbox = context.resolve(DockerSandbox)

    async def __aenter__(self) -> Self:
        if self._sandbox is not None:
            await self._sandbox.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._sandbox is not None:
            await self._sandbox.close()


def create_tool_context(
    *dependencies: object,
    workspace: Workspace | None = None,
    workspace_root: Path | None = None,
    sandbox: CommandRunner | None = None,
    sandbox_environment: Mapping[str, str] | None = None,
    sandbox_mounts: Sequence[BindMount] = (),
    sandbox_network_access: bool = False,
) -> ToolContext:
    if workspace is not None and workspace_root is not None:
        raise ValueError("Provide either workspace or workspace_root, not both.")
    if sandbox is not None and (
        sandbox_environment or sandbox_mounts or sandbox_network_access
    ):
        raise ValueError(
            "Configure environment, mounts, and network access on the "
            "provided sandbox directly."
        )
    selected_workspace = workspace or _default_workspace(workspace_root)
    selected_sandbox = sandbox or _default_sandbox(
        selected_workspace.root,
        environment=sandbox_environment,
        mounts=sandbox_mounts,
        network_access=sandbox_network_access,
    )
    return ToolContext(selected_workspace, selected_sandbox, *dependencies)


def _default_workspace(root: Path | None = None) -> LocalWorkspace:
    selected_root = root if root is not None else CaraPaths().workspace_root
    return LocalWorkspace(selected_root, max_file_bytes=1_000_000)


def _default_sandbox(
    working_directory: Path,
    *,
    environment: Mapping[str, str] | None = None,
    mounts: Sequence[BindMount] = (),
    network_access: bool = False,
) -> DockerSandbox:
    workspace_target = PurePosixPath("/workspace")
    if any(
        mount.target == workspace_target or workspace_target in mount.target.parents
        for mount in mounts
    ):
        raise ValueError("'/workspace' and its children are reserved for Cara.")
    return DockerSandbox(
        _BASH_IMAGE,
        defaults=CommandDefaults(
            working_directory=working_directory,
            environment={"HOME": "/tmp", **(environment or {})},
            limits=CommandLimits(timeout_seconds=15, max_output_bytes=1_000_000),
        ),
        policy=SandboxPolicy.for_workspace(
            working_directory,
            enable_network_access=network_access,
            limits=SandboxLimits(
                memory_bytes=256 * 1024 * 1024,
                pids=64,
                cpus=1,
            ),
        ),
        mounts=mounts,
        shell="/bin/bash",
    )


def create_tools(context: ToolContext | None = None) -> _ManagedTools:
    selected_context = context if context is not None else create_tool_context()
    tools = _new_tools(selected_context)
    register_tools(tools)
    return tools


def _new_tools(context: ToolContext) -> _ManagedTools:
    return _ManagedTools(context)


def build_tools(
    *dependencies: object,
    skills: Skills | None = None,
    workspace: Workspace | None = None,
    workspace_root: Path | None = None,
    sandbox_environment: Mapping[str, str] | None = None,
    sandbox_mounts: Sequence[BindMount] = (),
    sandbox_network_access: bool = False,
    tools: agenttoolkit.Tools | None = None,
) -> _ManagedTools:
    configured_dependencies = [
        *dependencies,
        IpLocationClient(),
        OpenMeteoClient(),
        TavilySearchClient(),
    ]
    if skills is not None:
        configured_dependencies.append(skills)
    tool_context = create_tool_context(
        *configured_dependencies,
        workspace=workspace,
        workspace_root=workspace_root,
        sandbox_environment=sandbox_environment,
        sandbox_mounts=sandbox_mounts,
        sandbox_network_access=sandbox_network_access,
    )
    if tools is None:
        return create_tools(tool_context)
    configured_tools = _new_tools(tool_context)
    configured_tools.merge(tools)
    return configured_tools


def register_tools(tools: agenttoolkit.Tools) -> None:
    @tools.action(
        description=(
            "Load a skill's full instructions into context before carrying "
            "out a task it covers. "
            "Call this first whenever a request matches one of the listed skills."
        ),
        params=LoadSkillParams,
        available_when=requires(Skills, predicate=lambda skills: len(skills) > 0),
    )
    async def load_skill(params: LoadSkillParams, skills: Inject[Skills]) -> str:
        loaded = skills.load(params.name)
        return loaded.instructions

    @tools.action(
        description=(
            "Look up the weather for the current location or a given "
            "place. Only use params.location when a specific place is "
            "explicitly asked about."
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
        description=("Search the web for current information, news, or facts."),
        params=WebSearchParams,
    )
    async def web_search(
        params: WebSearchParams, client: Inject[TavilySearchClient]
    ) -> str:
        response = await client.search(params.query, max_results=params.max_results)
        return _render_search_response(response)

    @tools.action(
        description=(
            "Search older daily notes and durable memory. Returns concise "
            "original excerpts with their source and date, ordered by relevance."
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
        return render_memory_results(results)

    @tools.action(
        description="Execute a Bash command in the isolated workspace sandbox.",
        params=BashParams,
    )
    async def bash(params: BashParams, sandbox: Inject[CommandRunner]) -> str:
        result = await sandbox.execute(params.command)
        result.check_returncode()
        return result.output.rstrip() or "(no output)"

    @tools.action(
        description=(
            "List files and directories under a workspace path. Directories "
            "end with a slash. The application workspace instructions "
            "describe the available mounted directories."
        ),
        params=ListFilesParams,
    )
    async def list_files(params: ListFilesParams, workspace: Inject[Workspace]) -> str:
        entries = await workspace.list_dir(params.path)
        return _render_entries(entries, empty="(empty)")

    @tools.action(
        description=(
            "Find workspace files and directories whose paths match a glob pattern."
        ),
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
                for line_number, line in enumerate(
                    match.context_before, start=first_context_line
                )
            )
            rendered.append(f"{match.path}:{match.line_number}:{match.line}")
            rendered.extend(
                f"{match.path}-{line_number}-{line}"
                for line_number, line in enumerate(
                    match.context_after, start=match.line_number + 1
                )
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
        description=(
            "Replace an exact snippet in an existing file. "
            "old_text must occur exactly once."
        ),
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
    table = "\n".join(
        ["| Uhrzeit | Wetter | Temp | Regen |", "| --- | --- | --- | --- |", *rows]
    )
    return f"{summary}\n\n{table}"


def _render_search_response(response: SearchResponse) -> str:
    if response.answer is None and not response.results:
        return "Keine Ergebnisse gefunden."
    parts = [response.answer] if response.answer else []
    parts.extend(
        f"{result.title} ({result.url}): {result.content}"
        for result in response.results
    )
    return "\n\n".join(parts)


def _render_entries(entries: Sequence[Entry], *, empty: str) -> str:
    rendered = [f"{entry.path}/" if entry.is_dir else entry.path for entry in entries]
    return "\n".join(rendered) if rendered else empty
