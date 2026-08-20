from agenttoolkit import Inject, Tools
from agenttoolkit.builtins import CommandRunner
from pydantic import Field

from agent.tools.params import ToolParams


class ShellParams(ToolParams):
    command: str = Field(
        description="Shell command to execute inside the isolated workspace sandbox."
    )


def register_shell_tools(tools: Tools) -> None:
    @tools.action(
        description="Execute a shell command in the isolated workspace sandbox.",
        params=ShellParams,
    )
    async def shell(params: ShellParams, sandbox: Inject[CommandRunner]) -> str:
        result = await sandbox.execute(params.command)
        result.check_returncode()
        return result.output.rstrip() or "(no output)"
