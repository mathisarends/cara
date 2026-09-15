from collections.abc import Callable

import pytest
from agenttoolkit import ToolContext

from agent.sandbox import SandboxDefinition
from agent.tools import AgentTools
from agent.tools.factory import _create_tool_context, _create_tools


@pytest.fixture
def project_sandbox() -> SandboxDefinition:
    return SandboxDefinition.model_validate(
        {
            "image": "cara-bash-sandbox:latest",
            "shell": "/bin/bash",
            "network_access": True,
            "defaults": {
                "home": "/tmp",
                "timeout_seconds": 15,
                "max_output_bytes": 1_000_000,
            },
            "limits": {
                "memory_bytes": 536_870_912,
                "pids": 512,
                "cpus": 1,
            },
            "reserved_targets": ["/workspace"],
        }
    )


@pytest.fixture
def make_tool_context() -> Callable[..., ToolContext]:
    """Builds tool contexts that `build_tools` does not expose, e.g. with a runner."""
    return _create_tool_context


@pytest.fixture
def make_tools() -> Callable[..., AgentTools]:
    return _create_tools
