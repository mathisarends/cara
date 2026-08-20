from collections.abc import Sequence

from agenttoolkit import (
    Inject,
    Skills,
    Tools,
    provided,
    requires,
)
from agenttoolkit.builtins import CommandRunner, Workspace
from agenttoolkit.builtins.fs import Entry

from agent.models import ModelSwitch
from agent.tools.handler import (
    LocationLookup,
    Weather,
    WeatherReport,
    WebSearch,
)
from agent.tools.middleware import ToolError
from agent.tools.params import (
    EditFileParams,
    GlobParams,
    GrepParams,
    ListFilesParams,
    LoadSkillParams,
    ReadFileParams,
    ShellParams,
    SwitchModelParams,
    VolumeParams,
    WeatherParams,
    WebSearchParams,
    WriteFileParams,
)
from voice.audio import VolumeControl


def register_tools(tools: Tools) -> None:
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
        try:
            loaded = skills.load(params.name)
        except ValueError as error:
            raise ToolError(str(error)) from None
        return loaded.instructions

    @tools.action(
        description="Get the name of the model currently driving this conversation.",
        available_when=requires(
            ModelSwitch, predicate=lambda models: models.has_alternatives
        ),
    )
    async def current_model(models: Inject[ModelSwitch]) -> str:
        return models.current_name

    @tools.action(
        description="List the models available to switch to.",
        available_when=requires(
            ModelSwitch, predicate=lambda models: models.has_alternatives
        ),
    )
    async def list_models(models: Inject[ModelSwitch]) -> str:
        return ", ".join(models.names)

    @tools.action(
        description="Switch the model driving this conversation.",
        params=SwitchModelParams,
        available_when=requires(
            ModelSwitch, predicate=lambda models: models.has_alternatives
        ),
    )
    async def switch_model(
        params: SwitchModelParams, models: Inject[ModelSwitch]
    ) -> str:
        try:
            models.switch(params.name)
        except ValueError as error:
            raise ToolError(str(error)) from None
        return f"Switched to {params.name}."

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
        location_client: Inject[LocationLookup],
        weather_client: Inject[Weather],
    ) -> str:
        if params.location:
            location = await weather_client.locate(params.location)
            if location is None:
                return f"No place named '{params.location}' was found."
        else:
            location = await location_client.current()
        report = await weather_client.current(location)
        return _render_weather_report(report)

    @tools.action(
        description=("Search the web for current information, news, or facts."),
        params=WebSearchParams,
    )
    async def web_search(params: WebSearchParams, websearch: Inject[WebSearch]) -> str:
        response = await websearch.search(params.query, max_results=params.max_results)
        return response.summary()

    @tools.action(
        description=(
            "Read the current playback volume in percent. Call this before a "
            "relative change such as 'a bit quieter'."
        ),
        available_when=provided(VolumeControl),
    )
    async def get_volume(control: Inject[VolumeControl]) -> str:
        return _render_volume(await control.get_volume())

    @tools.action(
        description="Set the playback volume to a percentage.",
        params=VolumeParams,
        available_when=provided(VolumeControl),
    )
    async def set_volume(params: VolumeParams, control: Inject[VolumeControl]) -> str:
        await control.set_volume(params.volume)
        return _render_volume(params.volume)

    @tools.action(
        description="Execute a shell command in the isolated workspace sandbox.",
        params=ShellParams,
    )
    async def shell(params: ShellParams, sandbox: Inject[CommandRunner]) -> str:
        result = await sandbox.execute(params.command)
        result.check_returncode()
        return result.output.rstrip() or "(no output)"

    @tools.action(
        description=(
            "List files and directories under a workspace path. Directories "
            "end with a slash. Paths are relative to the workspace root; use "
            "'.' for that root, never '/'."
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


def _render_volume(volume: int) -> str:
    return f"Lautstärke: {volume} %."


def _render_weather_report(report: WeatherReport) -> str:
    parts = [f"**{round(report.temperature_c)} °C**"]
    if abs(report.temperature_c - report.apparent_temperature_c) >= 2:
        parts.append(f"feels like {round(report.apparent_temperature_c)} °C")
    parts.append(report.description)
    parts.append(f"Wind {round(report.wind_speed_kmh)} km/h")
    summary = f"## Weather in {report.location_name}\n\n" + ", ".join(parts) + "."

    if not report.hourly:
        return summary

    rows = (
        f"| {hour.time:%H:%M} | {hour.description} | {round(hour.temperature_c)} °C | "
        f"{hour.precipitation_probability}% |"
        for hour in report.hourly
    )
    table = "\n".join(
        ["| Time | Weather | Temp | Rain |", "| --- | --- | --- | --- |", *rows]
    )
    return f"{summary}\n\n{table}"


def _render_entries(entries: Sequence[Entry], *, empty: str) -> str:
    rendered = [f"{entry.path}/" if entry.is_dir else entry.path for entry in entries]
    return "\n".join(rendered) if rendered else empty
