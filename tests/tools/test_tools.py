import asyncio
from pathlib import Path
from tempfile import gettempdir

from agenttoolkit import Tools
from agenttoolkit.builtins import CommandResult, LocalWorkspace, SandboxPolicy, Workspace

from cara.audio import AudioOutput, AudioPlayer
from cara.tools import create_tool_context, create_tools


class SilentOutput:
    def __init__(self, output: AudioOutput) -> None:
        self._output = output
        self.volume = 1.0

    @property
    def output(self) -> AudioOutput:
        return self._output

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        pass

    async def get_volume(self) -> float:
        return self.volume

    async def set_volume(self, volume: float) -> None:
        self.volume = volume


def test_audio_tools_follow_injected_player_availability() -> None:
    context = create_tool_context(AudioPlayer(SilentOutput(AudioOutput.LOCAL)))
    tools = create_tools(context)

    available = {schema.name for schema in tools.get_schema()}
    assert "get_volume" in available
    assert "set_audio_output" not in available

    context.provide(AudioPlayer(SilentOutput(AudioOutput.LOCAL), SilentOutput(AudioOutput.SONOS)))

    assert "set_audio_output" in {schema.name for schema in tools.get_schema()}


def test_custom_action_uses_agenttoolkit_execution() -> None:
    tools = Tools()

    @tools.action(description="Echo a message.")
    async def echo(message: str) -> str:
        return message

    result = asyncio.run(tools.execute("echo", {"message": "hi"}))

    assert result == "hi"


def test_workspace_tools_use_agenttoolkit_local_workspace(tmp_path: Path) -> None:
    workspace = LocalWorkspace(tmp_path)
    tools = create_tools(create_tool_context(workspace=workspace))

    write_result = asyncio.run(tools.execute("write_file", {"path": "notes/a.txt", "content": "hello"}))
    read_result = asyncio.run(tools.execute("read_file", {"path": "notes/a.txt"}))
    edit_result = asyncio.run(
        tools.execute(
            "edit_file",
            {"path": "notes/a.txt", "old_text": "hello", "new_text": "hello toolkit"},
        )
    )

    assert write_result == "Wrote notes/a.txt."
    assert read_result == "hello"
    assert edit_result == "Edited notes/a.txt."
    assert asyncio.run(workspace.read_file("notes/a.txt")) == "hello toolkit"


def test_glob_tool_uses_agenttoolkit_workspace_matching(tmp_path: Path) -> None:
    workspace = LocalWorkspace(tmp_path)
    asyncio.run(workspace.write_file("src/app.py", "print('app')\n"))
    asyncio.run(workspace.write_file("src/readme.md", "docs\n"))
    asyncio.run(workspace.write_file("tests/test_app.py", "def test_app(): pass\n"))
    tools = create_tools(create_tool_context(workspace=workspace))

    result = asyncio.run(tools.execute("glob", {"pattern": "**/*.py", "max_results": 1}))

    assert result == "src/app.py"


def test_grep_tool_uses_agenttoolkit_workspace_search(tmp_path: Path) -> None:
    workspace = LocalWorkspace(tmp_path)
    asyncio.run(workspace.write_file("src/app.py", "before\nNeedle here\nafter\n"))
    asyncio.run(workspace.write_file("src/readme.md", "needle in docs\n"))
    tools = create_tools(create_tool_context(workspace=workspace))

    result = asyncio.run(
        tools.execute(
            "grep",
            {
                "pattern": "needle",
                "glob": "**/*.py",
                "case_sensitive": False,
                "context_lines": 1,
            },
        )
    )

    assert result == "src/app.py-1-before\nsrc/app.py:2:Needle here\nsrc/app.py-3-after"


def test_default_error_middleware_handles_workspace_errors(tmp_path: Path) -> None:
    result = asyncio.run(
        create_tools(create_tool_context(workspace=LocalWorkspace(tmp_path))).execute(
            "write_file",
            {"path": "../outside.txt", "content": "blocked"},
        )
    )

    assert result.startswith("Tool failed:")


def test_bash_tool_delegates_to_agenttoolkit_sandbox(tmp_path: Path) -> None:
    class RecordingSandbox:
        def __init__(self) -> None:
            self.policy = SandboxPolicy.for_workspace(tmp_path)
            self.command: str | None = None

        async def execute(self, command: str, **kwargs) -> CommandResult:
            self.command = command
            return CommandResult(
                command=command,
                returncode=0,
                stdout="hello from sandbox\n",
                stderr="",
                duration_seconds=0.01,
            )

    sandbox = RecordingSandbox()
    context = create_tool_context(workspace=LocalWorkspace(tmp_path), sandbox=sandbox)
    tools = create_tools(context)

    result = asyncio.run(tools.execute("bash", {"command": "printf hello"}))

    assert result == "hello from sandbox"
    assert sandbox.command == "printf hello"


def test_default_workspace_is_an_agenttoolkit_workspace() -> None:
    context = create_tool_context()
    workspace = context.resolve(Workspace)

    assert workspace is not None
    assert workspace.root == (Path(gettempdir()) / "cara" / "workspace").resolve()


def test_default_workspace_mounts_memory_content_directory() -> None:
    tools = create_tools()

    result = asyncio.run(tools.execute("list_files", {"path": "/memory"}))

    assert "/memory/USER.md" in result.splitlines()


def test_default_workspace_accepts_writable_additional_mounts(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    tools = create_tools(create_tool_context(workspace_mounts={"/skills": skills_root}))

    result = asyncio.run(
        tools.execute(
            "write_file",
            {"path": "/skills/example/SKILL.md", "content": "# Example\n"},
        )
    )
    memory = asyncio.run(tools.execute("list_files", {"path": "/memory"}))

    assert result == "Wrote /skills/example/SKILL.md."
    assert (skills_root / "example" / "SKILL.md").read_text(encoding="utf-8") == "# Example\n"
    assert "/memory/USER.md" in memory.splitlines()


def test_to_schema_returns_openai_function_schema() -> None:
    schema = next(item for item in create_tools().get_schema("openai") if item["function"]["name"] == "bash")

    assert schema["type"] == "function"
    assert schema["function"]["parameters"]["properties"]["command"]["type"] == "string"
