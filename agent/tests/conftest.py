from collections.abc import Callable

import pytest
from agenttoolkit import ToolContext
from agenttoolkit.builtins import (
    CommandDefaults,
    CommandRunner,
    LocalShellRunner,
    LocalWorkspace,
    Workspace,
)

from agent.clock import LocalClock
from agent.tools import AgentTools
from agent.tools.factory import _create_tools


@pytest.fixture
def make_tool_context(tmp_path) -> Callable[..., ToolContext]:
    def create(
        *dependencies: object,
        workspace: Workspace | None = None,
        runner: CommandRunner | None = None,
        clock: LocalClock | None = None,
    ) -> ToolContext:
        selected_workspace = workspace or LocalWorkspace(tmp_path)
        selected_runner = runner or LocalShellRunner(
            CommandDefaults(working_directory=selected_workspace.root)
        )
        return ToolContext(
            selected_workspace,
            selected_runner,
            clock or LocalClock(),
            *dependencies,
        )

    return create


@pytest.fixture
def make_tools() -> Callable[..., AgentTools]:
    return _create_tools
