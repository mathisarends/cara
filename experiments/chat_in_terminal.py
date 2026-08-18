import asyncio
import os
from pathlib import Path

from agenttoolkit import Skills
from agenttoolkit.builtins import BindMount, LocalWorkspace
from dotenv import load_dotenv

from agent import Agent
from agent.tools import build_tools
from experiments.agent_runner import AgentTurnRunner
from experiments.terminal import TerminalSession
from llm import CodexModel, create_codex_model

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_ROOT = _PROJECT_ROOT / "skills"
_WORKSPACE_ROOT = _PROJECT_ROOT / "workspace"
_AGENT_SRC = _PROJECT_ROOT / "agent" / "src" / "agent"
_EXPERIMENTS_ROOT = _PROJECT_ROOT / "experiments"

load_dotenv()


async def main() -> None:
    skills = Skills.from_dir(_SKILLS_ROOT)
    llm = create_codex_model(CodexModel.TERRA)

    async with build_tools(
        skills=skills,
        workspace=_create_workspace(),
        sandbox_environment={"SPOGO_CONFIG": "/etc/spogo.toml"},
        sandbox_mounts=(
            *_editable_sandbox_mounts(),
            BindMount.read_write(_spogo_config_root(), "/spogo"),
            BindMount.read_only(
                _PROJECT_ROOT / "docker" / "spogo.toml", "/etc/spogo.toml"
            ),
        ),
        sandbox_network_access=True,
    ) as tools:
        agent = Agent(
            llm=llm,
            tools=tools,
            prompt_root=_WORKSPACE_ROOT,
            skills=skills,
        )

        session = TerminalSession(AgentTurnRunner(agent))
        await session.run()


def _create_workspace() -> LocalWorkspace:
    return LocalWorkspace(
        _WORKSPACE_ROOT,
        mounts={
            "/src/agent": _AGENT_SRC,
            "/experiments": _EXPERIMENTS_ROOT,
            "/skills": _SKILLS_ROOT,
        },
    )


def _editable_sandbox_mounts() -> tuple[BindMount, ...]:
    return (
        BindMount.read_write(_AGENT_SRC, "/src/agent"),
        BindMount.read_write(_EXPERIMENTS_ROOT, "/experiments"),
        BindMount.read_write(_SKILLS_ROOT, "/skills"),
    )


def _spogo_config_root() -> Path:
    app_data = os.environ.get("APPDATA")
    if app_data is None:
        raise RuntimeError(
            "APPDATA is required to locate the Spogo configuration on Windows."
        )
    config_root = Path(app_data) / "spogo"
    if not config_root.is_dir():
        raise FileNotFoundError(
            f"Spogo configuration directory does not exist: {config_root}"
        )
    return config_root


if __name__ == "__main__":
    asyncio.run(main())
