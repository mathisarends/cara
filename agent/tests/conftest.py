from collections.abc import Callable

import pytest
from agenttoolkit import ToolContext

from agent.tools import AgentTools
from agent.tools.factory import _create_tool_context, _create_tools


@pytest.fixture
def make_tool_context() -> Callable[..., ToolContext]:
    """Builds tool contexts that `build_tools` does not expose, e.g. with a runner."""
    return _create_tool_context


@pytest.fixture
def make_tools() -> Callable[..., AgentTools]:
    return _create_tools
