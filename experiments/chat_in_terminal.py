import asyncio
import os
from pathlib import Path

from agenttoolkit import Skills
from agenttoolkit.builtins import BindMount
from dotenv import load_dotenv
from llmify import ChatCodex

from cara import Agent, TerminalSession
from cara.tools import build_tools

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROJECT_ROOT / "skills"
WORKSPACE_ROOT = PROJECT_ROOT / "workspace"

load_dotenv()


def _spogo_config_root() -> Path:
    app_data = os.environ.get("APPDATA")
    if app_data is None:
        raise RuntimeError("APPDATA is required to locate the Spogo configuration on Windows.")
    config_root = Path(app_data) / "spogo"
    if not config_root.is_dir():
        raise FileNotFoundError(f"Spogo configuration directory does not exist: {config_root}")
    return config_root


async def main() -> None:
    skills = Skills.from_dir(SKILLS_ROOT)
    llm = ChatCodex.from_cli(model="gpt-5.6-terra")

    async with build_tools(
        skills=skills,
        workspace_mounts={"/skills": SKILLS_ROOT},
        sandbox_environment={"SPOGO_CONFIG": "/etc/spogo.toml"},
        sandbox_mounts=(
            BindMount.read_write(_spogo_config_root(), "/spogo"),
            BindMount.read_only(PROJECT_ROOT / "docker" / "spogo.toml", "/etc/spogo.toml"),
        ),
        sandbox_network_access=True,
    ) as tools:
        agent = Agent(
            llm=llm,
            tools=tools,
            prompt_root=WORKSPACE_ROOT,
            skills=skills,
            extend_system_prompt=(
                "Die lokalen Skills sind unter `/skills` schreibbar eingebunden. "
                "Lies bestehende Dateien vor Änderungen und speichere neue oder geänderte Skills dort."
            ),
        )

        terminal_session = TerminalSession(agent)
        await terminal_session.run()


if __name__ == "__main__":
    asyncio.run(main())
