import asyncio
from pathlib import Path

import pytest
from agenttoolkit import Tools
from agenttoolkit.builtins import (
    CommandResult,
    DockerSandbox,
    LocalWorkspace,
    SandboxPolicy,
    Workspace,
)

from agent.tools import (
    BindMount,
    SandboxConfig,
    build_tools,
    create_tool_context,
    create_tools,
)


def test_custom_action_uses_agenttoolkit_execution() -> None:
    tools = Tools()

    @tools.action(description="Echo a message.")
    async def echo(message: str) -> str:
        return message

    result = asyncio.run(tools.execute("echo", {"message": "hi"}))

    assert result == "hi"


def test_build_tools_registers_core_and_additional_tools(tmp_path: Path) -> None:
    additional_tools = Tools()

    @additional_tools.action(description="Echo a message.")
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
    tools = create_tools(create_tool_context(workspace=workspace))

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
    tools = create_tools(create_tool_context(workspace=workspace))

    result = asyncio.run(
        tools.execute("glob", {"pattern": "**/*.py", "max_results": 1})
    )

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


def test_shell_tool_delegates_to_agenttoolkit_sandbox(tmp_path: Path) -> None:
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
    context = create_tool_context(
        workspace=LocalWorkspace(tmp_path), sandbox=SandboxConfig(runner=sandbox)
    )
    tools = create_tools(context)

    result = asyncio.run(tools.execute("shell", {"command": "printf hello"}))

    assert result == "hello from sandbox"
    assert sandbox.command == "printf hello"


def test_agent_tools_prepare_and_close_default_docker_sandbox(monkeypatch) -> None:
    opened: list[DockerSandbox] = []
    closed: list[DockerSandbox] = []

    async def open_sandbox(sandbox: DockerSandbox) -> None:
        opened.append(sandbox)

    async def close_sandbox(sandbox: DockerSandbox) -> None:
        closed.append(sandbox)

    monkeypatch.setattr(DockerSandbox, "open", open_sandbox)
    monkeypatch.setattr(DockerSandbox, "close", close_sandbox)

    async def run() -> None:
        context = create_tool_context()
        sandbox = context.resolve(DockerSandbox)
        tools = create_tools(context)

        await tools.prepare()
        assert opened == [sandbox]
        assert closed == []
        await tools.aclose()
        assert closed == [sandbox]

    asyncio.run(run())


def test_default_workspace_is_an_agenttoolkit_workspace() -> None:
    context = create_tool_context()
    workspace = context.resolve(Workspace)
    sandbox = context.resolve(DockerSandbox)

    assert workspace is not None
    assert workspace.root == Path.cwd()
    assert sandbox is not None
    assert sandbox.defaults.working_directory == workspace.root
    assert sandbox.policy.allows_write(workspace.root)
    workspace_mount = next(
        argument
        for argument in sandbox.build_open_argv(container_name="test")
        if "dst=/workspace" in argument
    )
    assert not workspace_mount.endswith(",readonly")


def test_sandbox_accepts_explicit_mounts_and_network_access(tmp_path: Path) -> None:
    config_root = tmp_path / "spogo"
    config_root.mkdir()
    mount = BindMount.read_write(config_root, "/tmp/.config/spogo")

    context = create_tool_context(
        sandbox=SandboxConfig(
            environment={"SPOGO_CONFIG": "/etc/spogo.toml"},
            mounts=(mount,),
            network_access=True,
        )
    )
    sandbox = context.resolve(DockerSandbox)

    assert sandbox is not None
    assert sandbox.defaults.environment["SPOGO_CONFIG"] == "/etc/spogo.toml"
    assert sandbox.mounts == (mount,)
    assert sandbox.policy.enable_network_access


def test_sandbox_mounts_have_explicit_access_modes(tmp_path: Path) -> None:
    music = tmp_path / "music"
    projects = tmp_path / "projects"
    music.mkdir()
    projects.mkdir()
    mounts = (
        BindMount.read_only(music, "/music"),
        BindMount.read_write(projects, "/projects"),
    )

    context = create_tool_context(sandbox=SandboxConfig(mounts=mounts))
    sandbox = context.resolve(DockerSandbox)

    assert sandbox is not None
    assert sandbox.mounts == mounts
    assert not sandbox.mounts[0].writable
    assert sandbox.mounts[1].writable
    arguments = sandbox.build_open_argv(container_name="test")
    music_mount = next(argument for argument in arguments if "dst=/music" in argument)
    projects_mount = next(
        argument for argument in arguments if "dst=/projects" in argument
    )
    assert music_mount.endswith(",readonly")
    assert not projects_mount.endswith(",readonly")


def test_workspace_container_accepts_nested_mounts(tmp_path: Path) -> None:
    mount = BindMount.read_write(tmp_path, "/workspace/projects")

    context = create_tool_context(sandbox=SandboxConfig(mounts=(mount,)))

    sandbox = context.resolve(DockerSandbox)
    assert sandbox is not None
    assert sandbox.mounts == (mount,)


def test_primary_workspace_container_target_is_reserved(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="primary workspace"):
        create_tool_context(
            sandbox=SandboxConfig(
                mounts=(BindMount.read_write(tmp_path, "/workspace"),)
            )
        )


def test_to_schema_returns_openai_function_schema() -> None:
    schema = next(
        item
        for item in create_tools().get_schema("openai")
        if item["function"]["name"] == "shell"
    )

    assert schema["type"] == "function"
    assert schema["function"]["parameters"]["properties"]["command"]["type"] == "string"
