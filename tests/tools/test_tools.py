import asyncio
import inspect
import logging
from pathlib import Path
from tempfile import gettempdir
from typing import Annotated, Literal

from pydantic import Field

from cara.audio import AudioOutput, AudioPlayer
from cara.file_system import Workspace
from cara.tools import ActionKind, ActionResult, EndSessionParams, Inject, ToolContext, ToolParams, Tools
from cara.tools.handler import BashSandboxError, BashSandboxResult


class Greeting:
    def __init__(self, text: str) -> None:
        self.text = text


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


class SearchParams(ToolParams):
    query: str = Field(description="Search query")
    limit: int = 10
    tags: list[str] = Field(default_factory=list, min_length=1, max_length=3)


def test_tools_does_not_accept_additional_middlewares() -> None:
    assert "middlewares" not in inspect.signature(Tools).parameters


def test_default_end_session_tool_returns_farewell() -> None:
    tools = Tools()

    result = asyncio.run(
        tools.execute(
            "end_session",
            {"farewell": "Bis bald!"},
        )
    )

    assert result == ActionResult.success("Bis bald!")


def test_default_end_session_tool_is_tagged_with_kind() -> None:
    tools = Tools()
    end_session = tools.get("end_session")

    assert end_session is not None
    assert end_session.param_model is EndSessionParams
    assert end_session.kind is ActionKind.END_SESSION


def test_default_set_audio_output_tool_switches_the_injected_player() -> None:
    player = AudioPlayer(SilentOutput(AudioOutput.LOCAL), SilentOutput(AudioOutput.SONOS))
    tools = Tools()
    tools.provide(player)

    result = asyncio.run(
        tools.execute(
            "set_audio_output",
            {"output": "sonos"},
        )
    )

    assert result == ActionResult.success("Audio output switched to 'sonos'.")
    assert player.active_output is AudioOutput.SONOS


def test_audio_output_tool_is_only_available_for_multiple_configured_outputs() -> None:
    tools = Tools()
    tools.provide(AudioPlayer(SilentOutput(AudioOutput.LOCAL)))

    assert tools.get("set_audio_output") is None
    assert all(schema["function"]["name"] != "set_audio_output" for schema in tools.to_schema())


def test_audio_output_tool_description_lists_the_configured_outputs() -> None:
    tools = Tools()
    tools.provide(AudioPlayer(SilentOutput(AudioOutput.LOCAL), SilentOutput(AudioOutput.SONOS)))

    schema = next(item for item in tools.to_schema() if item["function"]["name"] == "set_audio_output")

    assert schema["function"]["description"].endswith("Available output names: local, sonos.")


def test_default_set_volume_tool_updates_the_injected_player() -> None:
    player = AudioPlayer(SilentOutput(AudioOutput.LOCAL))
    tools = Tools()
    tools.provide(player)

    result = asyncio.run(tools.execute("set_volume", {"level": 0.4}))

    assert result == ActionResult.success("Lautstärke ist jetzt 40%.")
    assert asyncio.run(player.get_volume()) == 0.4


def test_default_get_volume_tool_reads_the_injected_player() -> None:
    player = AudioPlayer(SilentOutput(AudioOutput.LOCAL))
    asyncio.run(player.set_volume(0.7))
    tools = Tools()
    tools.provide(player)

    result = asyncio.run(tools.execute("get_volume", {}))

    assert result == ActionResult.success("0.70")


def test_volume_tools_are_unavailable_without_a_configured_player() -> None:
    tools = Tools()

    assert tools.get("get_volume") is None
    assert tools.get("set_volume") is None


def test_action_decorator_registers_tool() -> None:
    tools = Tools()

    @tools.action(description="Echo a message.")
    async def echo(message: str) -> ActionResult:
        return ActionResult.success(message)

    result = asyncio.run(tools.execute("echo", {"message": "hi"}))

    assert result == ActionResult.success("hi")
    assert tools.get("echo") is not None


def test_replacing_context_preserves_configured_workspace(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = Tools(workspace=workspace)

    tools.set_context(ToolContext())

    assert tools.resolve(Workspace) is workspace


def test_default_workspace_is_an_isolated_temporary_directory() -> None:
    workspace = Tools().resolve(Workspace)

    assert workspace is not None
    assert workspace.root == (Path(gettempdir()) / "cara" / "workspace").resolve()


def test_default_bash_tool_runs_without_an_allow_list(tmp_path: Path) -> None:
    invocation: dict[str, object] = {}

    class Sandbox:
        async def run(self, command: str, workspace: Workspace) -> BashSandboxResult:
            invocation["command"] = command
            invocation["workspace"] = workspace
            return BashSandboxResult(return_code=0, output="hello from sandbox")

    workspace = Workspace(tmp_path)
    tools = Tools(workspace=workspace, bash_sandbox=Sandbox())

    result = asyncio.run(
        tools.execute(
            "bash",
            {"command": "printf 'hello from bash'"},
        )
    )

    assert result == ActionResult.success("hello from sandbox")
    assert invocation == {"command": "printf 'hello from bash'", "workspace": workspace}


def test_unknown_tool_is_logged(caplog) -> None:
    tools = Tools()

    with caplog.at_level(logging.WARNING, logger="cara.tools.executor"):
        result = asyncio.run(tools.execute("unknown", {"value": "test"}))

    assert not result.ok
    assert any(message.startswith("Rejected unavailable tool 'unknown'.") for message in caplog.messages)


def test_bash_tool_passes_shell_syntax_to_sandbox() -> None:
    invocation: dict[str, str] = {}

    class Sandbox:
        async def run(self, command: str, workspace: Workspace) -> BashSandboxResult:
            invocation["command"] = command
            return BashSandboxResult(return_code=7, output="failure details")

    tools = Tools(bash_sandbox=Sandbox())

    result = asyncio.run(
        tools.execute(
            "bash",
            {"command": "printf 'failure details' >&2; exit 7"},
        )
    )

    assert result == ActionResult.fail("Command exited with status 7.\nfailure details")
    assert invocation["command"] == "printf 'failure details' >&2; exit 7"


def test_bash_tool_returns_sandbox_startup_error() -> None:
    class Sandbox:
        async def run(self, command: str, workspace: Workspace) -> BashSandboxResult:
            raise BashSandboxError("Docker is unavailable.")

    result = asyncio.run(Tools(bash_sandbox=Sandbox()).execute("bash", {"command": "rg needle"}))

    assert result == ActionResult.fail("Docker is unavailable.")


def test_default_bash_tool_schema_describes_guarded_command() -> None:
    tools = Tools()

    schema = next(item for item in tools.to_schema() if item["function"]["name"] == "bash")

    assert schema["function"]["parameters"]["properties"]["command"] == {
        "description": "Bash command to execute inside the isolated workspace sandbox.",
        "type": "string",
    }
    assert schema["function"]["parameters"]["required"] == ["command"]


def test_action_decorator_supports_pydantic_params() -> None:
    tools = Tools()

    @tools.action(params=SearchParams)
    async def search(params: SearchParams) -> ActionResult:
        return ActionResult.success(f"{params.query}:{params.limit}")

    result = asyncio.run(tools.execute("search", {"query": "songs"}))

    assert result == ActionResult.success("songs:10")


def test_to_schema_returns_openai_compatible_function_schema() -> None:
    tools = Tools()

    @tools.action(description="Pick a song.")
    async def pick_song(
        greeting: Inject[Greeting],
        title: Annotated[str, "Song title"],
        mood: Literal["calm", "bright"] = "calm",
    ) -> ActionResult:
        return ActionResult.success(f"{greeting.text}: {title} ({mood})")

    schema = next(item for item in tools.to_schema() if item["function"]["name"] == "pick_song")

    assert schema == {
        "type": "function",
        "function": {
            "name": "pick_song",
            "description": "Pick a song.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"description": "Song title", "type": "string"},
                    "mood": {"type": "string", "enum": ["calm", "bright"]},
                },
                "required": ["title"],
            },
        },
    }


def test_to_schema_uses_pydantic_param_model() -> None:
    tools = Tools()

    @tools.action(params=SearchParams)
    async def search(params: SearchParams) -> ActionResult:
        return ActionResult.success(params.query)

    schema = next(item for item in tools.to_schema() if item["function"]["name"] == "search")

    parameters = schema["function"]["parameters"]

    assert parameters["type"] == "object"
    assert parameters["properties"]["query"] == {"description": "Search query", "type": "string"}
    assert parameters["properties"]["limit"] == {"type": "integer", "default": 10}
    assert parameters["properties"]["tags"] == {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 1,
        "maxItems": 3,
    }
    assert parameters["required"] == ["query"]
