from collections.abc import Sequence

from agenttoolkit import Inject, Tools
from agenttoolkit.builtins import Workspace
from agenttoolkit.builtins.fs import Entry
from pydantic import Field

from agent.tools.params import ToolParams


class ListFilesParams(ToolParams):
    path: str = Field(
        default=".",
        description=(
            "Directory to list, relative to the workspace root. Defaults to the root."
        ),
    )


class GlobParams(ToolParams):
    pattern: str = Field(
        description=(
            "Glob pattern relative to the workspace root, for example '**/*.py'."
        )
    )
    max_results: int = Field(
        default=200,
        ge=1,
        le=1_000,
        description="Maximum number of matching paths to return.",
    )


class GrepParams(ToolParams):
    pattern: str = Field(
        description="Regular expression to search for in workspace files."
    )
    glob: str | None = Field(
        default=None, description="Optional glob restricting which files are searched."
    )
    case_sensitive: bool = Field(
        default=True, description="Whether matching is case-sensitive."
    )
    context_lines: int = Field(
        default=0,
        ge=0,
        le=10,
        description=(
            "Number of surrounding lines to include before and after each match."
        ),
    )
    max_matches: int = Field(
        default=100,
        ge=1,
        le=1_000,
        description="Maximum number of matches to return.",
    )


class ReadFileParams(ToolParams):
    path: str = Field(
        description="Path of the file to read, relative to the workspace root."
    )


class WriteFileParams(ToolParams):
    path: str = Field(
        description=(
            "Path of the file to create or overwrite, relative to the workspace root."
        )
    )
    content: str = Field(description="Full new contents of the file.")


class EditFileParams(ToolParams):
    path: str = Field(
        description="Path of the file to edit, relative to the workspace root."
    )
    old_text: str = Field(
        description="Exact text to replace. Must occur exactly once in the file."
    )
    new_text: str = Field(description="Text to insert in place of old_text.")


def register_filesystem_tools(tools: Tools) -> None:
    @tools.tool(
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

    @tools.tool(
        description=(
            "Find workspace files and directories whose paths match a glob pattern."
        ),
        params=GlobParams,
    )
    async def glob(params: GlobParams, workspace: Inject[Workspace]) -> str:
        entries = await workspace.glob(params.pattern)
        return _render_entries(entries[: params.max_results], empty="(no matches)")

    @tools.tool(
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

    @tools.tool(description="Read a text file's full contents.", params=ReadFileParams)
    async def read_file(params: ReadFileParams, workspace: Inject[Workspace]) -> str:
        return await workspace.read_file(params.path)

    @tools.tool(
        description="Create a file or overwrite it entirely with new content.",
        params=WriteFileParams,
    )
    async def write_file(params: WriteFileParams, workspace: Inject[Workspace]) -> str:
        await workspace.write_file(params.path, params.content)
        return f"Wrote {params.path}."

    @tools.tool(
        description=(
            "Replace an exact snippet in an existing file. "
            "old_text must occur exactly once."
        ),
        params=EditFileParams,
    )
    async def edit_file(params: EditFileParams, workspace: Inject[Workspace]) -> str:
        await workspace.edit_file(params.path, params.old_text, params.new_text)
        return f"Edited {params.path}."


def _render_entries(entries: Sequence[Entry], *, empty: str) -> str:
    rendered = [f"{entry.path}/" if entry.is_dir else entry.path for entry in entries]
    return "\n".join(rendered) if rendered else empty
