from collections.abc import Sequence

from agenttoolkit import Inject, Skills, Tools, provided, requires
from agenttoolkit.builtins import CommandRunner, Workspace
from agenttoolkit.builtins.fs import Entry

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
