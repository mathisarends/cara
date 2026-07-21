import asyncio
from typing import TYPE_CHECKING, Protocol

from cara.audio import AudioPlayer
from cara.file_system import FileSystem, Workspace
from cara.skills import Skills
from cara.tools.di import Inject, ToolContext
from cara.tools.params import (
    BashParams,
    EditFileParams,
    EndSessionParams,
    ListFilesParams,
    LoadSkillParams,
    ReadFileParams,
    SetAudioOutputParams,
    WriteFileParams,
)
from cara.tools.views import ActionKind, ActionResult

if TYPE_CHECKING:
    from cara.tools.tools import Tools


class Toolset(Protocol):
    def register(self, tools: "Tools") -> None: ...


class CoreTools:
    def register(self, tools: "Tools") -> None:
        @tools.action(
            description=(
                "End the conversation when the user says goodbye or otherwise signals "
                "they are finished. Provide a short spoken farewell."
            ),
            params=EndSessionParams,
            kind=ActionKind.END_SESSION,
        )
        async def end_session(params: EndSessionParams) -> ActionResult:
            return ActionResult.success(params.farewell)

        @tools.action(
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


def _multiple_audio_outputs_available(context: ToolContext) -> bool:
    player = context.resolve(AudioPlayer)
    return player is not None and len(player.available_outputs) > 1


def _audio_output_tool_description(context: ToolContext) -> str:
    player = context.resolve(AudioPlayer)
    if player is None:
        return "Switch audio playback to another configured output strategy."
    available = ", ".join(output.value for output in player.available_outputs)
    return f"Switch audio playback to another configured output strategy. Available output names: {available}."


class AudioTools:
    def register(self, tools: "Tools") -> None:
        @tools.action(
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


class BashTools:
    def register(self, tools: "Tools") -> None:
        @tools.action(
            description=(
                "Execute one command allowed by the configured Bash policy in the workspace. "
                "Shell operators, redirects, substitutions, and command chaining are rejected."
            ),
            params=BashParams,
            kind=ActionKind.DESTRUCTIVE,
        )
        async def bash(params: BashParams, workspace: Inject[Workspace]) -> ActionResult:
            process = await asyncio.create_subprocess_exec(
                "bash",
                "-lc",
                params.command,
                cwd=workspace.root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await process.communicate()
            content = output.decode("utf-8", errors="replace").rstrip()
            return_code = process.returncode
            if return_code is None:
                return ActionResult.fail("Bash process ended without a return code.")
            if return_code != 0:
                detail = f"\n{content}" if content else ""
                return ActionResult.fail(f"Command exited with status {return_code}.{detail}")
            return ActionResult.success(content or "(no output)")


class FileSystemTools:
    def register(self, tools: "Tools") -> None:
        @tools.action(
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

        @tools.action(
            description="Read a text file's full contents.",
            params=ReadFileParams,
            kind=ActionKind.READ,
        )
        async def read_file(params: ReadFileParams, file_system: Inject[FileSystem]) -> ActionResult:
            if not file_system.exists(params.path):
                return ActionResult.fail(f"'{params.path}' does not exist.")
            return ActionResult.success(file_system.read_text(params.path))

        @tools.action(
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

        @tools.action(
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
