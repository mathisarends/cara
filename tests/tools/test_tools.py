import asyncio
import inspect
import logging
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from cara.audio import AudioOutput, AudioPlayer
from cara.file_system import Workspace
from cara.tools import ActionKind, ActionResult, EndSessionParams, Inject, ToolContext, ToolParams, Tools


class Greeting:
    def __init__(self, text: str) -> None:
        self.text = text


class SilentOutput:
    def __init__(self, output: AudioOutput) -> None:
        self._output = output

    @property
    def output(self) -> AudioOutput:
        return self._output

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        pass


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


def test_default_bash_tool_is_denied() -> None:
    tools = Tools()

    result = asyncio.run(
        tools.execute(
            "bash",
            {"command": "printf 'hello from bash'"},
        )
    )

    assert result == ActionResult.fail(
        "Bash execution is disabled by the current tool policy. "
        "Use the dedicated file tools or configure an explicit command allow-list."
    )


def test_unknown_tool_is_logged(caplog) -> None:
    tools = Tools()

    with caplog.at_level(logging.WARNING, logger="cara.tools.executor"):
        result = asyncio.run(tools.execute("unknown", {"value": "test"}))

    assert not result.ok
    assert any(message.startswith("Rejected unavailable tool 'unknown'.") for message in caplog.messages)


def test_bash_tool_rejects_shell_syntax_even_for_allowed_command() -> None:
    tools = Tools(bash_allowed_commands=("printf",))

    result = asyncio.run(
        tools.execute(
            "bash",
            {"command": "printf 'failure details' >&2; exit 7"},
        )
    )

    assert result == ActionResult.fail(
        "Shell operators, redirects, substitutions, and command chaining are not allowed. "
        "Run one allow-listed command without shell syntax."
    )


def test_allowed_bash_command_runs_at_workspace_root(monkeypatch, tmp_path: Path) -> None:
    invocation: dict[str, object] = {}

    class Process:
        returncode = 0

        async def communicate(self) -> tuple[bytes, None]:
            return b"result", None

    async def create_process(*args, **kwargs):
        invocation["args"] = args
        invocation["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    tools = Tools(workspace=Workspace(tmp_path), bash_allowed_commands=("rg",))

    result = asyncio.run(
        tools.execute(
            "bash",
            {"command": "rg needle"},
        )
    )

    assert result == ActionResult.success("result")
    assert invocation["args"] == ("bash", "-lc", "rg needle")
    assert invocation["kwargs"]["cwd"] == tmp_path.resolve()


def test_default_bash_tool_schema_describes_guarded_command() -> None:
    tools = Tools()

    schema = next(item for item in tools.to_schema() if item["function"]["name"] == "bash")

    assert schema["function"]["parameters"]["properties"]["command"] == {
        "description": "Single allow-listed command to execute in the workspace.",
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
