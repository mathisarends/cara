import asyncio
from pathlib import Path

from agenttoolkit import Skills
from agenttoolkit.builtins import LocalWorkspace
from dotenv import load_dotenv

from agent import Agent, ModelSwitch
from agent.sandbox import SandboxDefinition
from agent.tools import build_tools
from experiments.agent_runner import AgentTurnRunner
from experiments.terminal import TerminalSession
from llm import CodexModel, create_codex_model

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SKILLS_ROOT = _PROJECT_ROOT / "skills"
_AGENT_SRC = _PROJECT_ROOT / "agent" / "src" / "agent"
_EXPERIMENTS_ROOT = _PROJECT_ROOT / "experiments"
_SANDBOX_CONFIG = _PROJECT_ROOT / "sandbox.yml"

load_dotenv()


async def main() -> None:
    skills = Skills.from_dir(_SKILLS_ROOT)
    llm = create_codex_model(CodexModel.TERRA)
    sandbox = SandboxDefinition.from_yaml(_SANDBOX_CONFIG)
    workspace = _create_workspace(sandbox)

    tools = build_tools(
        skills=skills,
        workspace=workspace,
        sandbox=sandbox,
    )
    agent = Agent(
        models=ModelSwitch.single(llm),
        tools=tools,
        skills=skills,
        workspace_root=workspace.root,
    )

    session = TerminalSession(AgentTurnRunner(agent))
    await session.run()


def _create_workspace(
    sandbox: SandboxDefinition | None = None,
) -> LocalWorkspace:
    definition = sandbox or SandboxDefinition.from_yaml(_SANDBOX_CONFIG)
    return LocalWorkspace(
        definition.resolve_workspace_root(),
        mounts={
            "/src/agent": _AGENT_SRC,
            "/experiments": _EXPERIMENTS_ROOT,
            "/skills": _SKILLS_ROOT,
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
