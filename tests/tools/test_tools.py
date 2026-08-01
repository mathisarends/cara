import asyncio
from pathlib import Path
from tempfile import gettempdir

from agenttoolkit import ActionResult, ToolEffect, Tools
from agenttoolkit.builtins import LocalWorkspace, SandboxPolicy, SandboxResult, Workspace

from cara.audio import AudioOutput, AudioPlayer
from cara.tools import EndSessionParams, create_tool_context, create_tools, register_tools


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


def test_default_end_session_tool_returns_farewell_and_has_tag() -> None:
    tools = Tools(context=create_tool_context())
    register_tools(tools)

    result = asyncio.run(tools.execute("end_session", {"farewell": "Bis bald!"}))
    end_session = tools.get("end_session")

    assert result == ActionResult.success("Bis bald!")
    assert end_session is not None
    assert end_session.param_model is EndSessionParams
    assert "end_session" in end_session.tags


def test_audio_tools_follow_injected_player_availability() -> None:
    context = create_tool_context(AudioPlayer(SilentOutput(AudioOutput.LOCAL)))
    tools = create_tools(context)

    available = tools.get_available()
    assert tools.get("get_volume") in available
    assert tools.get("set_audio_output") not in available

    context.provide(AudioPlayer(SilentOutput(AudioOutput.LOCAL), SilentOutput(AudioOutput.SONOS)))

    assert tools.get("set_audio_output") in tools.get_available()


def test_custom_action_uses_agenttoolkit_execution() -> None:
    tools = Tools()

    @tools.action(description="Echo a message.")
    async def echo(message: str) -> ActionResult:
        return ActionResult.success(message)

    result = asyncio.run(tools.execute("echo", {"message": "hi"}))

    assert result == ActionResult.success("hi")


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

    assert write_result.ok
    assert read_result.result == "hello"
    assert edit_result.ok
    assert asyncio.run(workspace.read_file("notes/a.txt")) == "hello toolkit"


def test_default_error_middleware_handles_workspace_errors(tmp_path: Path) -> None:
    result = asyncio.run(
        create_tools(create_tool_context(workspace=LocalWorkspace(tmp_path))).execute(
            "write_file",
            {"path": "../outside.txt", "content": "blocked"},
        )
    )

    assert not result.ok
    assert result.error == "Internal tool error."


def test_bash_tool_delegates_to_agenttoolkit_sandbox(tmp_path: Path) -> None:
    class RecordingSandbox:
        def __init__(self) -> None:
            self.policy = SandboxPolicy.for_workspace(tmp_path)
            self.command: str | None = None

        async def execute(self, command: str, **kwargs) -> SandboxResult:
            self.command = command
            return SandboxResult(
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

    assert result == ActionResult.success("hello from sandbox")
    assert sandbox.command == "printf hello"
    bash = tools.get("bash")
    assert bash is not None
    assert bash.effects == frozenset((ToolEffect.SPAWNS_PROCESS, ToolEffect.WRITES_WORKSPACE))


def test_default_workspace_is_an_agenttoolkit_workspace() -> None:
    context = create_tool_context()
    workspace = context.resolve(Workspace)

    assert workspace is not None
    assert workspace.root == (Path(gettempdir()) / "cara" / "workspace").resolve()


def test_to_schema_returns_openai_function_schema() -> None:
    schema = next(item for item in create_tools().get_schema("openai") if item["function"]["name"] == "bash")

    assert schema["type"] == "function"
    assert schema["function"]["parameters"]["properties"]["command"]["type"] == "string"
