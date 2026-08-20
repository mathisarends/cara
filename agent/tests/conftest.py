from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from agenttoolkit import ToolContext

from agent.sandbox import SandboxDefinition
from agent.tools import AgentTools
from agent.tools.factory import _create_tool_context, _create_tools

_GATEWAY_CONFIG = Path(__file__).resolve().parents[2] / "gateway.yaml"


@pytest.fixture
def project_sandbox() -> SandboxDefinition:
    config = yaml.safe_load(_GATEWAY_CONFIG.read_text(encoding="utf-8"))
    return SandboxDefinition.model_validate(config["agent"]["config"]["sandbox"])


@pytest.fixture
def make_tool_context() -> Callable[..., ToolContext]:
    """Builds tool contexts that `build_tools` does not expose, e.g. with a runner."""
    return _create_tool_context


@pytest.fixture
def make_tools() -> Callable[..., AgentTools]:
    return _create_tools
