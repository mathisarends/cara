import asyncio
from pathlib import Path

from agenttoolkit import Skills
from agenttoolkit.builtins import BindMount, LocalWorkspace
from dotenv import load_dotenv

from agent import Agent
from agent.sandbox import SandboxConfig
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

    tools = build_tools(
        skills=skills,
        workspace=_create_workspace(),
        sandbox=SandboxConfig(
            mounts=_editable_sandbox_mounts(),
            network_access=True,
        ),
    )
    agent = Agent(
        llm=llm,
        tools=tools,
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


if __name__ == "__main__":
    asyncio.run(main())
