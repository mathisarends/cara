import asyncio
import logging
from pathlib import Path

import pytest
from agenttoolkit import Tools
from agenttoolkit.builtins import (
    CommandResult,
    CommandRunner,
    DockerSandbox,
    LocalShellRunner,
    LocalWorkspace,
    SandboxPolicy,
    Workspace,
)

from agent.sandbox import BindMount, SandboxDefinition, create_sandbox
from agent.tools import build_tools


def test_custom_action_uses_agenttoolkit_execution() -> None:
    tools = Tools()

    @tools.tool(description="Echo a message.")
    async def echo(message: str) -> str:
        return message

    result = asyncio.run(tools.execute("echo", {"message": "hi"}))

    assert result == "hi"


def test_build_tools_registers_core_and_additional_tools(tmp_path: Path) -> None:
    additional_tools = Tools()

    @additional_tools.tool(description="Echo a message.")
    async def echo(message: str) -> str:
        return message

    tools = build_tools(
        workspace=LocalWorkspace(tmp_path),
        additional_tools=additional_tools,
    )

    assert tools.get("shell") is not None
    assert tools.get("echo") is not None


def test_workspace_tools_use_agenttoolkit_local_workspace(tmp_path: Path) -> None:
    workspace = LocalWorkspace(tmp_path)
    tools = build_tools(workspace=workspace)

    write_result = asyncio.run(
        tools.execute("write_file", {"path": "notes/a.txt", "content": "hello"})
    )
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
    tools = build_tools(workspace=workspace)

    result = asyncio.run(
        tools.execute("glob", {"pattern": "**/*.py", "max_results": 1})
    )

    assert result == "src/app.py"


def test_grep_tool_uses_agenttoolkit_workspace_search(tmp_path: Path) -> None:
    workspace = LocalWorkspace(tmp_path)
    asyncio.run(workspace.write_file("src/app.py", "before\nNeedle here\nafter\n"))
    asyncio.run(workspace.write_file("src/readme.md", "needle in docs\n"))
    tools = build_tools(workspace=workspace)

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
        build_tools(workspace=LocalWorkspace(tmp_path)).execute(
            "write_file",
            {"path": "../outside.txt", "content": "blocked"},
        )
    )

    assert result.startswith("Tool failed:")


def test_shell_tool_delegates_to_agenttoolkit_sandbox(
    tmp_path: Path, make_tool_context, make_tools
) -> None:
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
    context = make_tool_context(workspace=LocalWorkspace(tmp_path), runner=sandbox)
    tools = make_tools(context)

    result = asyncio.run(tools.execute("shell", {"command": "printf hello"}))

    assert result == "hello from sandbox"
    assert sandbox.command == "printf hello"


def test_expected_shell_failure_logs_one_warning_without_traceback(
    tmp_path: Path, caplog, make_tool_context, make_tools
) -> None:
    class FailingSandbox:
        policy = SandboxPolicy.for_workspace(tmp_path)

        async def execute(self, command: str, **kwargs) -> CommandResult:
            return CommandResult(
                command=command,
                returncode=1,
                stdout="",
                stderr="no speakers found\n",
                duration_seconds=0.01,
            )

    context = make_tool_context(
        workspace=LocalWorkspace(tmp_path), runner=FailingSandbox()
    )
    tools = make_tools(context)

    with caplog.at_level(logging.INFO, logger="agent.tools.middleware"):
        result = asyncio.run(tools.execute("shell", {"command": "sonos group solo"}))

    records = [
        record for record in caplog.records if record.name == "agent.tools.middleware"
    ]
    assert result.endswith("no speakers found")
    assert len(records) == 2
    assert "shell called with arguments" in records[0].getMessage()
    assert records[1].levelno == logging.WARNING
    assert "shell failed" in records[1].getMessage()
    assert all("finished" not in record.getMessage() for record in records)
    assert not records[1].exc_info


def test_invalid_tool_input_is_returned_and_logged_on_one_line(caplog) -> None:
    tools = build_tools()

    with caplog.at_level(logging.INFO, logger="agent.tools.middleware"):
        result = asyncio.run(
            tools.execute(
                "shell",
                {"command": "sonos search spotify", "max_results": 5},
            )
        )

    records = [
        record for record in caplog.records if record.name == "agent.tools.middleware"
    ]
    assert result.startswith("Tool failed: 1 validation error for ShellParams")
    assert len(records) == 2
    assert "shell called with arguments" in records[0].getMessage()
    assert records[1].levelno == logging.WARNING
    assert "Extra inputs are not permitted" in records[1].getMessage()
    assert "\n" not in records[1].getMessage()
    assert not records[1].exc_info


def test_unexpected_tool_exception_is_logged_and_propagated(caplog) -> None:
    additional_tools = Tools()

    @additional_tools.tool(description="Crash unexpectedly.")
    def explode() -> str:
        raise RuntimeError("broken implementation")

    tools = build_tools(additional_tools=additional_tools)

    with (
        caplog.at_level(logging.INFO, logger="agent.tools.middleware"),
        pytest.raises(RuntimeError, match="broken implementation"),
    ):
        asyncio.run(tools.execute("explode"))

    records = [
        record for record in caplog.records if record.name == "agent.tools.middleware"
    ]
    assert len(records) == 2
    assert "explode called with arguments" in records[0].getMessage()
    assert records[1].levelno == logging.ERROR
    assert "explode crashed" in records[1].getMessage()
    assert records[1].exc_info is not None


def test_successful_tool_output_is_truncated_on_debug(caplog) -> None:
    additional_tools = Tools()

    @additional_tools.tool(description="Return a long result.")
    def long_result() -> str:
        return "x" * 400

    tools = build_tools(additional_tools=additional_tools)

    with caplog.at_level(logging.DEBUG, logger="agent.tools.middleware"):
        result = asyncio.run(tools.execute("long_result"))

    output_record = next(
        record
        for record in caplog.records
        if record.name == "agent.tools.middleware"
        and " output: " in record.getMessage()
    )
    message = output_record.getMessage()
    assert result == "x" * 400
    assert "x" * 300 in message
    assert "x" * 301 not in message


def test_agent_tools_prepare_and_close_default_docker_sandbox(
    monkeypatch, make_tool_context, make_tools, project_sandbox: SandboxDefinition
) -> None:
    opened: list[DockerSandbox] = []
    closed: list[DockerSandbox] = []

    async def open_sandbox(sandbox: DockerSandbox) -> None:
        opened.append(sandbox)

    async def close_sandbox(sandbox: DockerSandbox) -> None:
        closed.append(sandbox)

    monkeypatch.setattr(DockerSandbox, "open", open_sandbox)
    monkeypatch.setattr(DockerSandbox, "close", close_sandbox)

    async def run() -> None:
        context = make_tool_context(sandbox=project_sandbox)
        sandbox = context.resolve(DockerSandbox)
        tools = make_tools(context)

        await tools.prepare()
        assert opened == [sandbox]
        assert closed == []
        await tools.aclose()
        assert closed == [sandbox]

    asyncio.run(run())


def test_context_without_sandbox_runs_commands_on_the_host(make_tool_context) -> None:
    context = make_tool_context()

    assert context.resolve(DockerSandbox) is None
    assert isinstance(context.resolve(CommandRunner), LocalShellRunner)


def test_default_workspace_is_an_agenttoolkit_workspace(
    make_tool_context,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project_sandbox: SandboxDefinition,
) -> None:
    monkeypatch.setenv("CARA_WORKSPACE_ROOT", str(tmp_path))
    context = make_tool_context(sandbox=project_sandbox)
    workspace = context.resolve(Workspace)
    sandbox = context.resolve(DockerSandbox)

    assert workspace is not None
    assert workspace.root == tmp_path
    assert sandbox is not None
    assert sandbox.defaults.working_directory == workspace.root
    assert sandbox.policy.allows_write(workspace.root)
    workspace_mount = next(
        argument
        for argument in sandbox.build_open_argv(container_name="test")
        if "dst=/workspace" in argument
    )
    assert not workspace_mount.endswith(",readonly")


def test_sandbox_accepts_explicit_environment_and_mounts(
    tmp_path: Path, project_sandbox: SandboxDefinition
) -> None:
    config_root = tmp_path / "example-cli"
    config_root.mkdir()
    mount = BindMount.read_write(config_root, "/tmp/.config/example-cli")

    sandbox = create_sandbox(
        tmp_path,
        project_sandbox,
        environment={"EXAMPLE_CONFIG": "/etc/example.toml"},
        mounts=(mount,),
    )

    assert sandbox.defaults.environment["EXAMPLE_CONFIG"] == "/etc/example.toml"
    assert sandbox.mounts[-1:] == (mount,)


def test_sandbox_mounts_have_explicit_access_modes(
    tmp_path: Path, project_sandbox: SandboxDefinition
) -> None:
    music = tmp_path / "music"
    projects = tmp_path / "projects"
    music.mkdir()
    projects.mkdir()
    mounts = (
        BindMount.read_only(music, "/music"),
        BindMount.read_write(projects, "/projects"),
    )

    sandbox = create_sandbox(tmp_path, project_sandbox, mounts=mounts)

    assert sandbox.mounts[-len(mounts) :] == mounts
    assert not mounts[0].writable
    assert mounts[1].writable
    arguments = sandbox.build_open_argv(container_name="test")
    music_mount = next(argument for argument in arguments if "dst=/music" in argument)
    projects_mount = next(
        argument for argument in arguments if "dst=/projects" in argument
    )
    assert music_mount.endswith(",readonly")
    assert not projects_mount.endswith(",readonly")


def test_workspace_container_accepts_nested_mounts(
    tmp_path: Path, project_sandbox: SandboxDefinition
) -> None:
    mount = BindMount.read_write(tmp_path, "/workspace/projects")

    sandbox = create_sandbox(tmp_path, project_sandbox, mounts=(mount,))

    assert sandbox.mounts[-1:] == (mount,)


def test_primary_workspace_container_target_is_reserved(
    tmp_path: Path, project_sandbox: SandboxDefinition
) -> None:
    with pytest.raises(ValueError, match="reserved"):
        create_sandbox(
            tmp_path,
            project_sandbox,
            mounts=(BindMount.read_write(tmp_path, "/workspace"),),
        )


def test_to_schema_returns_openai_function_schema() -> None:
    schema = next(
        item
        for item in build_tools().get_schema("openai")
        if item["function"]["name"] == "shell"
    )

    assert schema["type"] == "function"
    assert schema["function"]["parameters"]["properties"]["command"]["type"] == "string"
