import asyncio
import logging
from pathlib import Path

import pytest
from agenttoolkit import Tools
from agenttoolkit.builtins import (
    CommandResult,
    CommandRunner,
    LocalShellRunner,
    LocalWorkspace,
    SandboxPolicy,
)

from gateway.agent_runtime.tools import build_tools


def test_custom_action_uses_agenttoolkit_execution() -> None:
    tools = Tools()

    @tools.tool(description="Echo a message.")
    async def echo(message: str) -> str:
        return message

    result = asyncio.run(tools.execute("echo", {"message": "hi"}))

    assert result == "hi"


def test_build_tools_registers_core_and_additional_tools(
    tmp_path: Path, make_tool_context
) -> None:
    additional_tools = Tools()

    @additional_tools.tool(description="Echo a message.")
    async def echo(message: str) -> str:
        return message

    tools = build_tools(
        context=make_tool_context(workspace=LocalWorkspace(tmp_path)),
        additional_tools=additional_tools,
    )

    assert tools.get("shell") is not None
    assert tools.get("echo") is not None


def test_workspace_tools_use_agenttoolkit_local_workspace(
    tmp_path: Path, make_tool_context
) -> None:
    workspace = LocalWorkspace(tmp_path)
    tools = build_tools(context=make_tool_context(workspace=workspace))

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


def test_glob_tool_uses_agenttoolkit_workspace_matching(
    tmp_path: Path, make_tool_context
) -> None:
    workspace = LocalWorkspace(tmp_path)
    asyncio.run(workspace.write_file("src/app.py", "print('app')\n"))
    asyncio.run(workspace.write_file("src/readme.md", "docs\n"))
    asyncio.run(workspace.write_file("tests/test_app.py", "def test_app(): pass\n"))
    tools = build_tools(context=make_tool_context(workspace=workspace))

    result = asyncio.run(
        tools.execute("glob", {"pattern": "**/*.py", "max_results": 1})
    )

    assert result == "src/app.py"


def test_grep_tool_uses_agenttoolkit_workspace_search(
    tmp_path: Path, make_tool_context
) -> None:
    workspace = LocalWorkspace(tmp_path)
    asyncio.run(workspace.write_file("src/app.py", "before\nNeedle here\nafter\n"))
    asyncio.run(workspace.write_file("src/readme.md", "needle in docs\n"))
    tools = build_tools(context=make_tool_context(workspace=workspace))

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


def test_default_error_middleware_handles_workspace_errors(
    tmp_path: Path, make_tool_context
) -> None:
    result = asyncio.run(
        build_tools(
            context=make_tool_context(workspace=LocalWorkspace(tmp_path))
        ).execute(
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


def test_invalid_tool_input_is_returned_and_logged_on_one_line(
    caplog, make_tool_context
) -> None:
    tools = build_tools(context=make_tool_context())

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


def test_unexpected_tool_exception_is_logged_and_propagated(
    caplog, make_tool_context
) -> None:
    additional_tools = Tools()

    @additional_tools.tool(description="Crash unexpectedly.")
    def explode() -> str:
        raise RuntimeError("broken implementation")

    tools = build_tools(context=make_tool_context(), additional_tools=additional_tools)

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


def test_successful_tool_output_is_truncated_on_debug(
    caplog, make_tool_context
) -> None:
    additional_tools = Tools()

    @additional_tools.tool(description="Return a long result.")
    def long_result() -> str:
        return "x" * 400

    tools = build_tools(context=make_tool_context(), additional_tools=additional_tools)

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


def test_context_without_sandbox_runs_commands_on_the_host(make_tool_context) -> None:
    context = make_tool_context()

    assert isinstance(context.resolve(CommandRunner), LocalShellRunner)


def test_to_schema_returns_openai_function_schema(make_tool_context) -> None:
    schema = next(
        item
        for item in build_tools(context=make_tool_context()).get_schema("openai")
        if item["function"]["name"] == "shell"
    )

    assert schema["type"] == "function"
    assert schema["function"]["parameters"]["properties"]["command"]["type"] == "string"
